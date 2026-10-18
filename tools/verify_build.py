#!/usr/bin/env python3
"""Read-only SDK/toolchain/component/image audit. Never opens a device."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from apply_idf_patches import PATCHES, check_sdk_version, git_apply_check
from package_candidate import ROOT, image_identity

SDK_COMMIT = 'b774170ff46c393eeb5e495ea37936038d3f4f4f'
COMPILER = 'esp-14.2.0_20260121'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()


def inside(path, roots):
    p = Path(path).resolve()
    return any(p == root or root in p.parents for root in roots)


def cache_values(path):
    return dict(re.findall(r'^([^/#\n:]+):[^=\n]+=(.*)$', path.read_text('utf-8'), re.M))


def verify(build, sdk):
    check_sdk_version(sdk)
    require(git(sdk, 'rev-parse', 'HEAD') == SDK_COMMIT, 'SDK commit differs from v5.5.5')
    require(git(sdk, 'diff', 'HEAD', '--name-only') == 'components/mbedtls/mbedtls',
            'Unexpected SDK changes (only the policy patch is allowed)')
    for target, patch in PATCHES:
        require(git_apply_check(sdk / target, ROOT / patch, reverse=True)[0], 'Required patch missing')
        require(git(sdk / target, 'diff', 'HEAD', '--name-only') == 'library/x509_crt.c',
                'Unexpected Mbed TLS changes')
        # Reverse the patch in memory: no unrelated changes to this file allowed.
        current = (sdk / target / 'library/x509_crt.c').read_bytes()
        original = subprocess.check_output(['git', '-C', str(sdk / target), 'show', 'HEAD:library/x509_crt.c'])
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            d = Path(temp); (d / 'library').mkdir()
            (d / 'library/x509_crt.c').write_bytes(current)
            subprocess.run(['git', 'apply', '--reverse', str(ROOT / patch)], cwd=d, check=True)
            restored = (d / 'library/x509_crt.c').read_bytes()
            require(restored.replace(b'\r\n', b'\n') == original.replace(b'\r\n', b'\n'),
                    'Mbed TLS contains changes outside the approved policy patch')
    submodules = {}
    for line in git(sdk, 'submodule', 'status', '--recursive').splitlines():
        require(not line.startswith(('+', 'U')), 'SDK submodule differs from the locked parent: ' + line)
        expected, path, *_ = line.strip().split()
        actual = git(sdk / path, 'rev-parse', 'HEAD')
        require(actual == expected.lstrip('+-'), 'SDK submodule mismatch: ' + path)
        require(not git(sdk / path, 'diff', 'HEAD', '--name-only') or path == 'components/mbedtls/mbedtls',
                'Unexpected submodule edits: ' + path)
        submodules[path] = actual

    description = json.loads((build / 'project_description.json').read_text('utf-8'))
    require(Path(description['idf_path']).resolve() == sdk, 'Project uses another SDK path')
    require(Path(description['project_path']).resolve() == ROOT, 'Project uses another source tree')
    require(description['target'] == 'esp32c3', 'Wrong target')
    compiler = Path(description['c_compiler'])
    compiler_version = subprocess.check_output([str(compiler), '--version'], text=True).splitlines()[0]
    require(COMPILER in compiler_version and '14.2.0' in compiler_version, 'Wrong compiler version')
    roots = [sdk, ROOT / 'components', ROOT / 'main', ROOT / 'code', build]
    for path in description['build_component_paths']:
        if not path:  # IDF includes an empty slot for its synthetic __idf_main.
            continue
        require(inside(path, roots), 'Foreign component: ' + path)
    count = 0
    dependencies = set()
    dependency_inputs = set()
    for directory in (build, build / 'bootloader'):
        cache = cache_values(directory / 'CMakeCache.txt')
        require(cache.get('CCACHE_ENABLE', '0') in ('0', 'OFF', 'FALSE'), 'Compiler cache must be disabled')
        require(Path(cache['CMAKE_TOOLCHAIN_FILE']).resolve() == sdk / 'tools/cmake/toolchain-esp32c3.cmake',
                'Wrong CMake toolchain')
        require(re.search(r'[/\\]idf5\.5_py[^/\\]+[/\\]', cache['PYTHON']), 'Wrong build Python')
        require(Path(cache['SDKCONFIG']).resolve() == Path(description['config_file']).resolve(),
                'Application and bootloader config differ')
        commands = json.loads((directory / 'compile_commands.json').read_text('utf-8'))
        for row in commands:
            require(inside(row['file'], roots), 'Foreign source: ' + row['file'])
            command = row['command'].replace('\\', '/')
            require(not re.search(r'(?i)(?:^|[/\s])ccache(?:\.exe)?\s', command), 'Cached compilation is not allowed')
            require(COMPILER in command, 'Foreign compiler in compilation database')
            require(not re.search(r'(?i)(idf6|idf-v6|v6\.0\.2|esp-15\.2|arduino)', command),
                    'Foreign framework/toolchain reference')
            for quoted, plain in re.findall(r'(?:^|\s)-I(?:"([^"]+)"|(\S+))', command):
                require(inside(quoted or plain, roots), 'Foreign include path: ' + (quoted or plain))
            count += 1
        deps = subprocess.check_output([cache['CMAKE_MAKE_PROGRAM'], '-C', str(directory), '-t', 'deps'], text=True)
        for line in deps.splitlines():
            if not line.startswith('    '): continue
            dep = Path(line.strip())
            if not dep.is_absolute(): dep = directory / dep
            if str(dep) in dependency_inputs: continue
            dependency_inputs.add(str(dep))
            require(inside(dep, [*roots, compiler.resolve().parent.parent]), 'Foreign included dependency: ' + str(dep))
            dependencies.add(str(dep.resolve()))

    config = Path(description['config_file']).read_text('utf-8')
    for setting in ('CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y', 'CONFIG_ESP_CONSOLE_SECONDARY_NONE=y',
                    'CONFIG_ESP_COREDUMP_DATA_FORMAT_ELF=y', 'CONFIG_ESP_COREDUMP_CHECKSUM_SHA256=y',
                    'CONFIG_MBEDTLS_CERTIFICATE_BUNDLE_DEFAULT_FULL=y'):
        require(setting in config, 'Required setting missing: ' + setting)
    require('CONFIG_MBEDTLS_CERTIFICATE_BUNDLE_CROSS_SIGNED_VERIFY=' not in config, 'IDF 6 Kconfig leaked')
    import importlib.util
    spec = importlib.util.spec_from_file_location('idf_partition_table', sdk / 'components/partition_table/gen_esp32part.py')
    partition_module = importlib.util.module_from_spec(spec); spec.loader.exec_module(partition_module)
    partition_bytes = (build / 'partition_table/partition-table.bin').read_bytes()
    partitions = partition_module.PartitionTable.from_binary(partition_bytes)
    partitions.verify(); partitions.verify_size_fits(0x400000)
    expected = partition_module.PartitionTable.from_csv((ROOT / 'partitions_ota_1m6.csv').read_text('utf-8'))
    require(expected.to_binary() == partition_bytes, 'Partition binary differs from source CSV')
    layout = {p.name: {'offset': p.offset, 'size': p.size} for p in partitions}
    require(layout['app0'] == {'offset': 0x10000, 'size': 0x1a0000} and
            layout['app1'] == {'offset': 0x1b0000, 'size': 0x1a0000}, 'OTA slot layout changed')
    for p in partitions:
        if p.name in ('nvs', 'smsdata'): require(p.type == 1 and p.subtype == 2, 'NVS partition changed')
    python_info = json.loads(subprocess.check_output([cache['PYTHON'], '-c',
        'import json,sys,importlib.metadata; print(json.dumps({"version":sys.version,"esptool":importlib.metadata.version("esptool")}))'], text=True))
    app = (build / description['app_bin']).read_bytes()
    identity = image_identity(app)
    require(identity['version'] == description['project_version'], 'Stale application image')
    config_header = (ROOT / 'components/idf_config/include/idf_config.h').read_text('utf-8')
    web_version = re.search(r'IDF_FW_VERSION\s*=\s*"([^"]+)"', config_header)
    require(web_version is not None and web_version.group(1) == identity['version'],
            'Web/status version differs from the application descriptor')
    files = [description['app_bin'], description['app_elf'], 'bootloader/bootloader.bin',
             'partition_table/partition-table.bin', 'compile_commands.json', 'bootloader/compile_commands.json']
    report = {'status': 'PASS', 'sdk': '5.5.5', 'sdk_commit': SDK_COMMIT, 'sdk_path': str(sdk),
              'mbedtls': '3.6.6', 'compiler': str(compiler), 'compiler_version': compiler_version,
              'python': cache['PYTHON'], 'source_root': str(ROOT), 'build_directory': str(build),
              'compile_units_checked': count, 'sdk_submodules': submodules, 'identity': identity,
              'header_dependencies_checked': len(dependencies), 'compiler_cache_enabled': False,
              'python_environment': python_info, 'partitions': layout,
              'files': {name: hashlib.sha256((build / name).read_bytes()).hexdigest() for name in files},
              'sdkconfig_sha256': hashlib.sha256(config.encode()).hexdigest(),
              'patches': {str(p): hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for _, p in PATCHES},
              'device_accessed': False, 'hardware_acceptance': False}
    (build / 'environment-audit.json').write_text(json.dumps(report, indent=2) + '\n', 'utf-8')
    print(f'PASS: SDK 5.5.5, {count} compile units, application/bootloader paths, config and image identity')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, default=ROOT / 'build/idf5.5.5')
    p.add_argument('--idf-path', type=Path, required=True)
    a = p.parse_args()
    verify(a.build.resolve(), a.idf_path.resolve())
