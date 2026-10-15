#!/usr/bin/env python3
"""在主机上检查 SDK 中真实 CA 回调的内存所有权及异常清理。

先运行 tools/apply_idf_patches.py，然后设置 IDF_PATH 或传入 --idf-path。
也可以通过 --source 指向单独的 esp_crt_bundle.c 文件。
此测试不模拟密码学验证，不能代替 ESP-IDF 构建或设备 HTTPS 回归。
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest


SOURCE_PATH: Path | None = None


def extract_function(source: str, name: str) -> str:
    """提取 SDK 顶层函数，避免测试另一份手工复制的实现。"""
    match = re.search(
        rf"^(?:static )?int {re.escape(name)}\([^{{]+\n\{{\n.*?^\}}$",
        source,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"SDK 中缺少预期函数 {name}；请先应用仓库补丁")
    return match.group(0)


# Extract the IDF 5.5.5 signature helper and verify callback. Crypto boundaries
# are fault-injected; this checks cleanup/verification flags, not cryptography.
HARNESS_PREFIX = r"""
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MBEDTLS_PRIVATE(x) x
#define likely(x) (x)
#define unlikely(x) (x)
#define ESP_LOGE(...) ((void)0)
#define ESP_LOGD(...) ((void)0)
#define ESP_LOGI(...) ((void)0)
#define MBEDTLS_MD_MAX_SIZE 64
#define MBEDTLS_ERR_PK_TYPE_MISMATCH (-2)
#define MBEDTLS_ERR_X509_FEATURE_UNAVAILABLE (-3)
#define MBEDTLS_ERR_X509_FATAL_ERROR (-6)
#define MBEDTLS_ERR_X509_CERT_VERIFY_FAILED (-7)
#define MBEDTLS_X509_BADCERT_BAD_MD 1
#define MBEDTLS_X509_BADCERT_NOT_TRUSTED 2
#define OTHER_VERIFY_ERROR 4
static int fault, live, found = 1;
static unsigned char root_key[4] = {1,2,3,4};
static const unsigned char *s_crt_bundle = root_key;
typedef const uint8_t *cert_t;
typedef struct { unsigned char *p; size_t len; } buf_t;
typedef struct { buf_t tbs, sig, issuer_raw; int sig_pk, sig_md; void *sig_opts; } mbedtls_x509_crt;
typedef struct { void *p; } mbedtls_pk_context;
typedef struct { int unused; } mbedtls_md_info_t;
static mbedtls_md_info_t info;
static void mbedtls_pk_init(mbedtls_pk_context *p) { p->p = NULL; }
static int mbedtls_pk_parse_public_key(mbedtls_pk_context *p, const uint8_t *b, size_t n) {
    p->p = malloc(16); assert(p->p); live++; return fault == 1 ? -1 : 0;
}
static int mbedtls_pk_can_do(mbedtls_pk_context *p, int type) { return fault != 2; }
static const mbedtls_md_info_t *mbedtls_md_info_from_type(int type) { return fault == 3 ? NULL : &info; }
static unsigned char mbedtls_md_get_size(const mbedtls_md_info_t *p) { return 32; }
static int mbedtls_md(const mbedtls_md_info_t *p, const unsigned char *s, size_t n, unsigned char *out) {
    memset(out, 0, 32); return fault == 4 ? -4 : 0;
}
static int mbedtls_pk_verify_ext(int type, void *opts, mbedtls_pk_context *p, int md,
    const unsigned char *hash, size_t n, const unsigned char *sig, size_t sn) { return fault == 5 ? -5 : 0; }
static void mbedtls_pk_free(mbedtls_pk_context *p) { if(p->p) { free(p->p); p->p = NULL; live--; } }
static cert_t esp_crt_find_cert(const unsigned char *p, size_t n) { return found ? root_key : NULL; }
static const uint8_t *esp_crt_get_key(cert_t c) { return c; }
static size_t esp_crt_get_key_len(cert_t c) { return 4; }
"""
HARNESS_SUFFIX = r"""
int main(void) {
    mbedtls_x509_crt crt = {0};
    for (int cycle = 0; cycle < 1000; cycle++) {
        for (fault = 0; fault < 6; fault++) {
            assert(esp_crt_check_signature(&crt, root_key, sizeof(root_key)) == -fault);
            assert(live == 0);
            uint32_t flags = MBEDTLS_X509_BADCERT_NOT_TRUSTED;
            int result = esp_crt_verify_callback(NULL, &crt, 0, &flags);
            assert(result == (fault ? MBEDTLS_ERR_X509_CERT_VERIFY_FAILED : 0));
            assert(flags == (fault ? MBEDTLS_X509_BADCERT_NOT_TRUSTED : 0));
            assert(live == 0);
        }
    }
    fault = 0;
    uint32_t flags = MBEDTLS_X509_BADCERT_NOT_TRUSTED | OTHER_VERIFY_ERROR;
    assert(esp_crt_verify_callback(NULL, &crt, 0, &flags) == 0);
    assert(flags == (MBEDTLS_X509_BADCERT_NOT_TRUSTED | OTHER_VERIFY_ERROR));
    flags = MBEDTLS_X509_BADCERT_NOT_TRUSTED; found = 0;
    assert(esp_crt_verify_callback(NULL, &crt, 0, &flags) == MBEDTLS_ERR_X509_CERT_VERIFY_FAILED);
    assert(flags == MBEDTLS_X509_BADCERT_NOT_TRUSTED);
    found = 1; s_crt_bundle = NULL;
    assert(esp_crt_verify_callback(NULL, &crt, 0, &flags) == MBEDTLS_ERR_X509_FATAL_ERROR);
    assert(flags == MBEDTLS_X509_BADCERT_NOT_TRUSTED); assert(live == 0);
    puts("PASS: 6000 callback cycles, all signature failure paths freed; trust flags preserved");
    return 0;
}
"""


class CertificateBundleCallbackTests(unittest.TestCase):
    def test_callback_memory_ownership(self) -> None:
        source_path = SOURCE_PATH
        if source_path is None:
            idf_path = os.environ.get("IDF_PATH")
            if not idf_path:
                self.skipTest("需要已打补丁的 SDK：设置 IDF_PATH 或使用 --idf-path/--source")
            source_path = (
                Path(idf_path) / "components/mbedtls/esp_crt_bundle/esp_crt_bundle.c"
            )
        self.assertTrue(source_path.is_file(), f"SDK 源文件不存在: {source_path}")
        compiler = shlex.split(os.environ.get("CC", "cc"))
        self.assertTrue(compiler and shutil.which(compiler[0]), "需要主机 C 编译器（CC 或 cc）")
        source = source_path.read_text(encoding="utf-8")
        functions = "\n\n".join(
            extract_function(source, name)
            for name in ("esp_crt_check_signature", "esp_crt_verify_callback")
        )
        with tempfile.TemporaryDirectory(prefix="crt-bundle-callback-") as directory:
            harness = Path(directory) / "callback.c"
            executable = Path(directory) / "callback"
            harness.write_text(HARNESS_PREFIX + functions + HARNESS_SUFFIX, encoding="utf-8")
            compile_result = subprocess.run(
                [
                    *compiler, "-std=c99", "-Wall", "-Wextra", "-Werror",
                    "-Wno-unused-parameter", "-Wno-unused-function",
                    *shlex.split(os.environ.get("CRT_BUNDLE_TEST_CFLAGS", "")),
                    str(harness), "-o", str(executable),
                ],
                capture_output=True, text=True, check=False, timeout=60,
            )
            self.assertEqual(compile_result.returncode, 0, compile_result.stdout + compile_result.stderr)
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, check=False, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS: 6000 callback cycles", result.stdout)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--idf-path", type=Path)
    inputs.add_argument("--source", type=Path)
    args, unittest_args = parser.parse_known_args()
    if args.source:
        SOURCE_PATH = args.source
    elif args.idf_path:
        SOURCE_PATH = args.idf_path / "components/mbedtls/esp_crt_bundle/esp_crt_bundle.c"
    unittest.main(argv=[__file__, *unittest_args])
