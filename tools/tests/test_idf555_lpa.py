"""Exercise the migrated production hash and HTTP callback with IDF 5.5.5.

The SHA-256 implementation is compiled from the selected SDK; HTTP and scanner
boundaries are stubs. No SIM, network or Profile changes are performed.
"""
import hashlib
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def function(source, name):
    return re.search(r'^static [^\n]+ ' + name + r'\([^\{]+\{\n.*?^\}', source, re.M | re.S).group()


PREFIX = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include "mbedtls/sha256.h"
using esp_err_t = int;
constexpr int ESP_OK=0, ESP_ERR_INVALID_RESPONSE=1, ESP_ERR_INVALID_SIZE=2, ESP_ERR_TIMEOUT=3;
constexpr int HTTP_EVENT_ON_HEADER=1, HTTP_EVENT_ON_DATA=2;
constexpr size_t kMaxBppEncodedBytes=100000;
static void clear_sensitive_bytes(std::vector<uint8_t>& v) { std::fill(v.begin(),v.end(),0); v.clear(); }
struct SensitiveBytes { std::vector<uint8_t> value; ~SensitiveBytes(){clear_sensitive_bytes(value);} };
struct Es9Deadline { bool expired() const { return false; } };
struct BppJsonStreamScanner {
    int feeds=0;
    int feed(const char*, size_t){ feeds++; return 0; }
    const char* failure_stage() const {return "";}
    size_t encoded_bpp_chars()const{return 0;} size_t decoded_bpp_bytes()const{return 0;}
    size_t parser_failure_offset()const{return 0;} const char* parser_failure_state()const{return "";}
    std::vector<uint8_t> parser_failure_header()const{return {};}
    size_t segment_count()const{return 0;}
};
struct Es9BppCapture {
    BppJsonStreamScanner* scanner=nullptr; std::string* scannerMessage=nullptr; Es9Deadline* deadline=nullptr;
    std::string adminProtocol; bool adminProtocolSeen=false; int scannerError=0;
    size_t responseBytes=0; int statusCode=-1; bool allowMissingProtocol=false, bodyPreflightChecked=false;
};
struct esp_http_client_event_t { int event_id; void* user_data; void* data; int data_len;
    const char* header_key; const char* header_value; int* client; };
static int esp_http_client_get_status_code(int* c){return *c;}
static bool equal_ascii_ci(const char* a,const char* b){return std::strcmp(a,b)==0;}
static bool check_rsp_protocol(const std::string& p,bool seen,bool allow,const char*,std::string& msg){
    if ((!seen && allow) || (seen && p=="gsma/rsp/v2.7.0")) return true;
    msg="invalid protocol"; return false;
}
static void idf_logf(const char*,...){}
static const char* esp_err_to_name(int){return "error";}
static std::string bpp_header_summary(const std::vector<uint8_t>&){return "";}
'''


class Lpa555Tests(unittest.TestCase):
    def test_hash_and_http_preflight(self):
        if not os.environ.get('IDF_PATH'):
            self.skipTest('IDF_PATH is required for native Mbed TLS source')
        sdk = Path(os.environ['IDF_PATH']) / 'components/mbedtls/mbedtls'
        source = (ROOT / 'components/idf_lpa/idf_lpa.cpp').read_text('utf-8')
        # Independent Python oracle, two binary transaction IDs and UTF-8 input.
        vectors = [('123456', bytes([0,1,255])), ('确认码', bytes(range(32)))]
        checks = []
        for code, tx in vectors:
            digest = hashlib.sha256(hashlib.sha256(code.encode()).digest() + tx).digest()
            code_bytes = ','.join(str(b) for b in code.encode())
            checks.append('''{ const unsigned char c[]={%s}; std::vector<uint8_t> tx={%s}, expected={%s};
                assert(compute_hash_cc(std::string(reinterpret_cast<const char*>(c),sizeof(c)),tx,out,msg));
                assert(out==expected); }''' % (code_bytes, ','.join(map(str,tx)), ','.join(map(str,digest))))
        main = r'''
int main(){
    std::vector<uint8_t> out={1,2}; std::string msg;
    assert(!compute_hash_cc("",{1},out,msg)); assert(out.empty());
    assert(!compute_hash_cc("123",{},out,msg)); assert(out.empty());
    HASH_CHECKS
    for (int status : {200,400,403,500}) for (int protocol : {0,1,2}) {
        BppJsonStreamScanner scanner; Es9BppCapture c; c.scanner=&scanner; c.scannerMessage=&msg;
        int code=status; char body[]="{}";
        esp_http_client_event_t e{HTTP_EVENT_ON_HEADER,&c,nullptr,0,"X-Admin-Protocol",
            protocol==1 ? "gsma/rsp/v2.7.0" : "wrong", &code};
        if(protocol) assert(es9_bpp_http_event_handler(&e)==ESP_OK);
        e.event_id=HTTP_EVENT_ON_DATA; e.data=body; e.data_len=2;
        const bool ok=status==200 && protocol==1;
        assert((es9_bpp_http_event_handler(&e)==ESP_OK)==ok);
        assert(c.statusCode==status); assert(scanner.feeds==(ok?1:0));
        assert(c.responseBytes==(ok?2:0));
    }
    return 0;
}
'''.replace('HASH_CHECKS', '\n'.join(checks))
        with tempfile.TemporaryDirectory() as name:
            d=Path(name); (d/'config.h').write_text('#define MBEDTLS_SHA256_C\n#define MBEDTLS_PLATFORM_C\n','utf-8')
            (d/'test.cpp').write_text(PREFIX + function(source,'compute_hash_cc') + '\n' +
                function(source,'es9_bpp_http_event_handler') + main, 'utf-8')
            includes = ['-I'+str(d), '-I'+str(sdk/'include'), '-DMBEDTLS_CONFIG_FILE="config.h"']
            cc=shlex.split(os.environ.get('CC','cc')); cxx=shlex.split(os.environ.get('CXX','c++'))
            objects=[]
            for name in ('sha256','platform_util','platform'):
                obj=d/(name+'.o'); objects.append(str(obj))
                result=subprocess.run([*cc,*includes,'-c',str(sdk/'library'/(name+'.c')),'-o',str(obj)],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
            exe=d/'test.exe'
            result=subprocess.run([*cxx,'-std=c++17',*includes,str(d/'test.cpp'),*objects,'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            subprocess.run([str(exe)],check=True,timeout=30)


if __name__=='__main__': unittest.main()
