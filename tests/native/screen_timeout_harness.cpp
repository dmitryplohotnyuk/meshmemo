// Host-side checks of the actual patched PowerFSM and its scheduler wrapper.
// Hardware-facing operations are stubbed; firmware code and arduino-fsm are compiled unchanged apart from includes.
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstdio>
#include <initializer_list>
#include "Fsm.h"

#define MESHTASTIC_EXCLUDE_POWER_FSM 0
#define LOG_POWERFSM(...) ((void)0)
#define LOG_INFO(...) ((void)0)
#define HAS_WIFI 0
#define meshtastic_Config_DeviceConfig_Role_ROUTER 2
#define meshtastic_Config_DeviceConfig_Role_ROUTER_LATE 3
static uint32_t ticks = 100;
unsigned long millis() { return ticks; }
struct {
    struct { uint32_t screen_on_secs = 2; } display;
    struct { int role = 0; } device;
    struct { bool is_power_saving = false; uint32_t sds_secs = 0, ls_secs = 0, on_battery_shutdown_after_secs = 0; } power;
} config;
constexpr uint32_t default_screen_on_secs = 60, default_broadcast_interval_secs = 900;
class Default {
public:
    static uint32_t getConfiguredOrDefaultMs(uint32_t);
    static uint32_t getConfiguredOrDefaultMs(uint32_t, uint32_t);
};
#include "Default.test.inc"
static bool bluetooth = true;
static unsigned bluetoothChanges = 0, sleeps = 0;
void setBluetoothEnable(bool enabled) { bluetooth = enabled; ++bluetoothChanges; }
void doDeepSleep(uint32_t, bool, bool) { ++sleeps; }
struct Power {};
uint32_t shutdownAtMsec = 0, timeLastPowered = 0;
struct PowerStatus { bool getHasUSB() { return true; } bool getHasBattery() { return true; } } powerStatusObject;
auto powerStatus = &powerStatusObject;
struct Screen {
    bool on = false;
    unsigned offCommands = 0;
    void setOn(bool enabled) { on = enabled; if (!enabled) ++offCommands; }
} display;
Screen *screen = &display;
namespace concurrency {
class OSThread {
public:
    bool canSleep = true;
    OSThread(const char *) {}
    virtual int32_t runOnce() = 0;
};
}
#include "PowerFSM.events.inc"
extern Fsm powerFSM;
extern State stateSERIAL, stateON, statePOWER, stateDARK;
#include "PowerFSM.test.inc"
#include "PowerFSMThread.test.inc"
class Runner : public concurrency::PowerFSMThread {
public: using concurrency::PowerFSMThread::runOnce;
};

int main()
{
    Runner runner;
    PowerFSM_setup();
    ticks += 3001;
    runner.runOnce();
    powerFSM.trigger(EVENT_SERIAL_CONNECTED);
    runner.runOnce();
    assert(powerFSM.getState() == &stateSERIAL && display.on && !bluetooth && !runner.canSleep);
    const auto start = ticks;
    for (unsigned i = 1; i < 20; ++i) {
        ticks = start + i * 100;
        powerFSM.trigger(EVENT_CONTACT_FROM_PHONE);
        powerFSM.trigger(EVENT_PACKET_FOR_PHONE);
        runner.runOnce();
        assert(display.on && !runner.canSleep);
    }
    const auto offBefore = display.offCommands;
    const auto bluetoothBefore = bluetoothChanges;
    ticks = start + 2000;
    runner.runOnce();
    assert(!display.on && display.offCommands == offBefore + 1);
    assert(powerFSM.getState() == &stateSERIAL && !runner.canSleep && !bluetooth);
    ticks += 10000;
    for (unsigned i = 0; i < 100; ++i) runner.runOnce();
    assert(display.offCommands == offBefore + 1 && bluetoothChanges == bluetoothBefore && sleeps == 0);

    // InputBroker wakes on EVENT_INPUT; legacy button uses EVENT_PRESS.
    for (int event : {EVENT_INPUT, EVENT_PRESS}) {
        powerFSM.trigger(event);
        runner.runOnce();
        assert(display.on && powerFSM.getState() == &stateSERIAL && !runner.canSleep);
        ticks += 1999; runner.runOnce(); assert(display.on);
        ++ticks; runner.runOnce(); assert(!display.on);
    }
    config.display.screen_on_secs = 0;
    powerFSM.trigger(EVENT_INPUT);
    ticks += default_screen_on_secs * 1000 - 1; runner.runOnce(); assert(display.on);
    ++ticks; runner.runOnce();
#ifdef USE_EINK
    assert(display.on); // Preserve the existing E-Ink zero-timeout convention.
#else
    assert(!display.on);
#endif
    config.display.screen_on_secs = UINT32_MAX;
    powerFSM.trigger(EVENT_INPUT);
    ticks += 0xF0000000U; runner.runOnce(); assert(display.on);

    config.display.screen_on_secs = 2;
    ticks = UINT32_MAX - 1000;
    powerFSM.trigger(EVENT_INPUT);
    ticks += 1999; runner.runOnce(); assert(display.on);
    ++ticks; runner.runOnce(); assert(!display.on && !runner.canSleep);

    screen = nullptr;
    powerFSM.trigger(EVENT_INPUT);
    ticks += 2000; runner.runOnce(); assert(powerFSM.getState() == &stateSERIAL);
    screen = &display;
    powerFSM.trigger(EVENT_SERIAL_DISCONNECTED);
    assert(powerFSM.getState() == &stateON && bluetooth);
    powerFSM.trigger(EVENT_SERIAL_CONNECTED);
    assert(powerFSM.getState() == &stateSERIAL && display.on && !bluetooth);
    powerFSM.trigger(EVENT_SHUTDOWN);
    assert(shutdownAtMsec == ticks);
    puts("PASS: timeout, USB keepalive, no CPU sleep, one-shot blanking, button/input wake, default/always-on, rollover, disconnect, shutdown");
}
