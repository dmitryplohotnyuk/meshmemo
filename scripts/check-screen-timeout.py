"""Compile the prepared firmware's actual power FSM with host hardware stubs.

Run after PlatformIO has installed arduino-fsm. MSVC requires a developer shell.
Generated files stay in .build; no device is accessed.
"""

import argparse
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def without_includes(source):
    return re.sub(r'^\s*#include[^\n]*', '', source, flags=re.MULTILINE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firmware', type=Path, default=ROOT / '.build/firmware')
    parser.add_argument('--cxx', default='c++')
    args = parser.parse_args()
    firmware = args.firmware.resolve()
    library = firmware / '.pio/libdeps/tbeam-s3-core/arduino-fsm'
    if not (library / 'Fsm.cpp').is_file():
        parser.error('Build the prepared tbeam-s3-core firmware first to install arduino-fsm.')
    output = ROOT / '.build/screen-timeout-test'
    output.mkdir(parents=True, exist_ok=True)
    for source, destination in [('PowerFSM.cpp', 'PowerFSM.test.inc'),
                                ('PowerFSMThread.h', 'PowerFSMThread.test.inc')]:
        (output / destination).write_text(without_includes((firmware / 'src' / source).read_text(encoding='utf-8')), encoding='utf-8')
    defaults = (firmware / 'src/mesh/Default.cpp').read_text(encoding='utf-8')
    (output / 'Default.test.inc').write_text(without_includes(defaults.split('uint32_t Default::getConfiguredOrDefault(')[0]), encoding='utf-8')
    events = (firmware / 'src/PowerFSM.h').read_text(encoding='utf-8')
    (output / 'PowerFSM.events.inc').write_text('\n'.join(re.findall(r'^#define EVENT_.*$', events, re.MULTILINE)) + '\n', encoding='utf-8')
    (output / 'WProgram.h').write_text('#pragma once\n#include <cstdlib>\n#include <cstddef>\nunsigned long millis();\n', encoding='utf-8')
    msvc = Path(args.cxx).stem.lower() == 'cl'
    sources = [str(ROOT / 'tests/native/screen_timeout_harness.cpp'), str(library / 'Fsm.cpp')]
    for eink in (False, True):
        executable = output / ('eink' if eink else 'oled')
        if msvc:
            executable = executable.with_suffix('.exe')
            command = [args.cxx, '/nologo', '/std:c++17', '/EHsc', '/W4',
                       '/I' + str(output), '/I' + str(library), *sources,
                       '/Fe:' + str(executable)] + (['/DUSE_EINK'] if eink else [])
        else:
            command = [args.cxx, '-std=c++17', '-Wall', '-Wextra', '-I', str(output),
                       '-I', str(library), *sources, '-o', str(executable)] + (['-DUSE_EINK'] if eink else [])
        subprocess.run(command, cwd=output, check=True)
        subprocess.run([str(executable)], cwd=output, check=True)


if __name__ == '__main__':
    main()
