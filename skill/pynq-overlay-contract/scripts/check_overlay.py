#!/usr/bin/env python3
"""Check PYNQ overlay metadata against an AXI peripheral contract."""
import argparse
import hashlib
import json
from pathlib import Path


def number(value):
    if isinstance(value, str):
        return int(value, 0)
    if type(value) is int:
        return value
    raise ValueError(f"Expected an integer or 0x string, got {value!r}")


def check(ip_dict, contract):
    expected = contract["ip"]
    if not isinstance(expected, dict) or not expected:
        raise ValueError("Contract ip must contain at least one instance")
    errors = []
    for name, spec in expected.items():
        entry = ip_dict.get(name)
        if entry is None:
            errors.append(f"{name}: instance not found")
            continue
        minimum = number(spec["min_range"])
        if minimum <= 0 or not spec["vlnv"]:
            raise ValueError(f"{name}: min_range and vlnv are required")
        if entry.get("type") != spec["vlnv"]:
            errors.append(f"{name}: VLNV {entry.get('type')!r}, expected {spec['vlnv']!r}")
        if "phys_addr" not in entry or "addr_range" not in entry:
            errors.append(f"{name}: missing CPU-visible address window")
            continue
        address = number(entry["phys_addr"])
        size = number(entry["addr_range"])
        if address < 0 or size < minimum:
            errors.append(f"{name}: invalid base address or address window smaller than {minimum} bytes")
        if "address" in spec and address != number(spec["address"]):
            errors.append(f"{name}: base address {address:#x}, expected {number(spec['address']):#x}")
        for register, value in spec.get("registers", {}).items():
            offset = number(value)
            metadata = entry.get("registers", {}).get(register, {})
            actual = metadata.get("address_offset")
            if offset < 0 or offset % 4 or offset + 4 > size:
                errors.append(f"{name}/{register}: requested offset outside aligned 32-bit window")
            if actual is None or number(actual) != offset:
                errors.append(f"{name}/{register}: offset {actual!r}, expected {offset:#x}")
    return errors


def load_metadata(bit):
    bit = bit.resolve()
    hwh = bit.with_suffix(".hwh")
    if bit.suffix.lower() != ".bit" or not bit.is_file() or not hwh.is_file():
        raise ValueError("Provide a .bit and its same-stem .hwh from the same Vivado build")
    if not bit.stat().st_size or not hwh.stat().st_size:
        raise ValueError("Bitstream or handoff file is empty")
    from pynq import Overlay

    overlay = Overlay(str(bit), download=False)
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (bit, hwh)}
    return overlay, hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--snapshot", type=Path, help="JSON snapshot shaped like Overlay.ip_dict")
    source.add_argument("--bit", type=Path, help="inspect metadata using PYNQ without downloading")
    args = parser.parse_args()
    try:
        contract = json.loads(args.contract.read_text(encoding="utf-8"))
        if args.snapshot:
            ip_dict = json.loads(args.snapshot.read_text(encoding="utf-8"))
            origin, hashes = "offline_snapshot", None
        else:
            overlay, hashes = load_metadata(args.bit)
            ip_dict, origin = overlay.ip_dict, "pynq_metadata_only"
        errors = check(ip_dict, contract)
    except (OSError, ImportError, KeyError, TypeError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Overlay input error: {error}\n")
    print(json.dumps(dict(source=origin, sha256=hashes, metadata_match=not errors, errors=errors), indent=2))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
