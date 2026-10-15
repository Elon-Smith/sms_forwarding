#!/usr/bin/env python3
"""Exercise actual HTTP SIM routing/URL decoding without a live device."""
from pathlib import Path
import os, re, shlex, subprocess, tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'components/idf_web/idf_web.cpp').read_text('utf-8')
def function(name):
    m=re.search(r'^(?:static )?(?:int|std::string|IdfFormFields|esp_err_t) '+name+r'\(',s,re.M)
    return s[m.start():s.index('\n}',m.end())+2]
code=r'''
#include <cassert>
#include <cstring>
#include <string>
#include <vector>
#include <utility>
#include <cstdio>
#include "idf_board.h"
using esp_err_t=int;using IdfFormFields=std::vector<std::pair<std::string,std::string>>;
constexpr int ESP_OK=0,HTTPD_400_BAD_REQUEST=400;
struct httpd_req_t {std::string query,header;void* user_ctx=nullptr;};
size_t httpd_req_get_url_query_len(httpd_req_t* req){return req->query.size();}
int httpd_req_get_url_query_str(httpd_req_t* req,char* out,size_t len){if(len<=req->query.size())return -1;std::strcpy(out,req->query.c_str());return 0;}
int httpd_resp_send_err(httpd_req_t*,int code,const char*){return code;}
void httpd_resp_set_hdr(httpd_req_t* req,const char*,const char* value){req->header=value;}
class WebInstance { public:
  IdfModemId sim_;explicit WebInstance(IdfModemId sim):sim_(sim){}
  using Handler=esp_err_t(WebInstance::*)(httpd_req_t*);
  static WebInstance& instance(IdfModemId sim);
  int route(httpd_req_t*){return sim_;}
// @functions@
};
WebInstance one(1),two(2);
WebInstance& WebInstance::instance(IdfModemId sim){return sim==1?one:two;}
int main(){
  WebInstance::Handler handler=&WebInstance::route;
  for(const auto& pair:std::vector<std::pair<std::string,int>>{
      {"",1},{"id=42",1},{"sim=1",1},{"sim=2&id=42",2},{"%73im=%32",2},
      {"sim=",400},{"sim=0",400},{"sim=3",400},{"sim=01",400},{"sim=-1",400},
      {"sim=2&sim=1",400},{"sim=2&%73im=2",400},{"sim=%002",400},{"sim=+2",400},
      {std::string(2048,'x'),400}}){
    httpd_req_t req{pair.first,"",&handler};int result=WebInstance::dispatch(&req);
    assert(result==pair.second);
    if(result!=400)assert(req.header==std::to_string(result));
  }
  puts("HTTP SIM routing: default SIM1, explicit SIM2, decoded/duplicate/invalid values and length boundary passed");
}
'''.replace('// @functions@','\n'.join(function(n) for n in ['hex_value','url_decode','parse_urlencoded','dispatch']))
with tempfile.TemporaryDirectory(prefix='dual-dispatch-') as tmp:
    cpp,binary=Path(tmp)/'test.cpp',Path(tmp)/'test.exe';cpp.write_text(code,'utf-8')
    subprocess.run([*shlex.split(os.environ.get('CXX','c++')),'-std=c++17','-Wall','-Wextra','-Werror','-I'+str(root/'components/idf_board/include'),str(cpp),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
