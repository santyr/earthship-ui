"""Passive ELF dependency metadata and explicit closure; never executes images."""
from pathlib import Path
import struct

import pytest


def module():
    from thermal_model import native_dependencies
    return native_dependencies


def elf(path, needed=(), *, endian='<', machine=62, interpreter=None):
    raw=bytearray(1024);raw[:16]=b'\x7fELF'+bytes([2,1 if endian=='<' else 2,1])+b'\0'*9
    count=3 if interpreter else 2
    raw[16:64]=struct.pack(endian+'HHIQQQIHHHHHH',3,machine,1,0,64,0,0,64,56,count,0,0,0)
    strings=b'\0';offsets=[]
    for name in needed:offsets.append(len(strings));strings+=name.encode()+b'\0'
    dynamic=[(1,index) for index in offsets]+[(5,0x400300),(10,len(strings)),(0,0)]
    raw[64:120]=struct.pack(endian+'IIQQQQQQ',1,4,0,0x400000,0x400000,len(raw),len(raw),4096)
    raw[120:176]=struct.pack(endian+'IIQQQQQQ',2,4,0x200,0x400200,0x400200,len(dynamic)*16,len(dynamic)*16,8)
    if interpreter:
        value=interpreter.encode()+b'\0';raw[0x180:0x180+len(value)]=value
        raw[176:232]=struct.pack(endian+'IIQQQQQQ',3,4,0x180,0x400180,0x400180,len(value),len(value),1)
    for index,pair in enumerate(dynamic):raw[0x200+index*16:0x210+index*16]=struct.pack(endian+'qQ',*pair)
    raw[0x300:0x300+len(strings)]=strings
    path.write_bytes(raw);path.chmod(0o600);return path


@pytest.mark.parametrize('endian',['<','>'])
def test_passive_reader_extracts_needed_and_interpreter(tmp_path,endian):
    path=elf(tmp_path/'image',('libfirst.so','libsecond.so'),endian=endian,interpreter='/reviewed/loader')
    result=module().elf_dependencies(path)
    assert result['needed']==['libfirst.so','libsecond.so']
    assert result['interpreter']=='/reviewed/loader'
    assert result['machine']==62


def test_explicit_library_map_resolves_transitive_cycles_without_execution(tmp_path):
    main=elf(tmp_path/'main',('liba.so',));a=elf(tmp_path/'a',('libb.so',));b=elf(tmp_path/'b',('liba.so',))
    result=module().native_dependency_closure([main],libraries={'liba.so':a,'libb.so':b})
    assert set(result['files'])=={str(main),str(a),str(b)}
    assert result['cold_environment_qualified'] is False
    assert result['production_qualified'] is False


@pytest.mark.parametrize('damage',['missing','architecture','loader','truncated','unsafe','size'])
def test_unsupported_or_unbound_native_dependencies_refuse(tmp_path,monkeypatch,damage):
    main=elf(tmp_path/'main',('liba.so',));a=elf(tmp_path/'a');mapping={'liba.so':a}
    if damage=='missing':mapping={}
    elif damage=='architecture':elf(a,machine=183)
    elif damage=='loader':elf(main,('liba.so',),interpreter='/unreviewed/loader')
    elif damage=='truncated':main.write_bytes(b'\x7fELF')
    elif damage=='unsafe':a.chmod(0o666)
    else:monkeypatch.setattr(module(),'MAX_NATIVE_FILES',1)
    with pytest.raises(ValueError):module().native_dependency_closure([main],libraries=mapping)


@pytest.mark.parametrize('damage',['class','header_count','string_address','needed_offset','missing_terminator'])
def test_malformed_elf_metadata_cannot_claim_closure(tmp_path,damage):
    path=elf(tmp_path/'image',('liba.so',));raw=bytearray(path.read_bytes())
    if damage=='class':raw[4]=1
    elif damage=='header_count':struct.pack_into('<H',raw,56,65535)
    elif damage=='string_address':struct.pack_into('<Q',raw,0x218,0xFFFFFFFFFFFFFFFF)
    elif damage=='needed_offset':struct.pack_into('<Q',raw,0x208,0xFFFFFFFFFFFFFFFF)
    else:raw[0x230:0x240]=struct.pack('<qQ',1,1)
    path.write_bytes(raw)
    with pytest.raises(ValueError):module().elf_dependencies(path)
