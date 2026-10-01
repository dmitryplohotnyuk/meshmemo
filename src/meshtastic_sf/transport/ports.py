"""Enumerate without opening ports; auto mode follows the previously verified USB device."""
import hashlib
from serial.tools import list_ports

USB_VENDORS = {0x303a,0x10c4,0x1a86,0x0403,0x239a,0x2e8a,0x0483}

def available_ports():
    result=[]
    for p in list_ports.comports():
        serial=(p.serial_number or '').replace(':','').replace('-','').lower()
        material=f'{p.vid}:{p.pid}:{serial or p.location or p.device}'
        result.append({'device':p.device,'description':p.description or p.device,
                       'candidate':p.vid in USB_VENDORS,
                       'identity':hashlib.sha256(material.encode()).hexdigest()})
    return sorted(result,key=lambda p:p['device'])

def select_port(settings, ports):
    if settings['mode']=='off':return None,'Подключение выключено'
    if settings['mode']=='manual':return settings['port'],None
    identity=settings['identity']
    candidates=[p for p in ports if (p['identity']==identity if identity else p['candidate'])]
    if len(candidates)==1:return candidates[0]['device'],None
    if not candidates:return None,'Ожидание USB-ноды'
    return None,'Найдено несколько устройств. Выберите порт вручную.'
