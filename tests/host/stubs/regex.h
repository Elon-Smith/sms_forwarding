#pragma once
#ifdef _WIN32
#include <regex>
#include <cstring>
using regex_t=std::regex*;
constexpr int REG_EXTENDED=1,REG_ICASE=2,REG_NOSUB=4;
inline int regcomp(regex_t* r,const char* p,int flags){
 try { *r=new std::regex(p,std::regex::extended | ((flags&REG_ICASE)?std::regex::icase:std::regex::flag_type{}));return 0; }
 catch(const std::regex_error&){*r=nullptr;return 1;}
}
inline int regexec(regex_t* r,const char* text,size_t,void*,int){return std::regex_search(text,**r)?0:1;}
inline void regfree(regex_t* r){delete *r;*r=nullptr;}
inline size_t regerror(int,regex_t*,char* msg,size_t n){const char* t="invalid regex";if(n){std::strncpy(msg,t,n);msg[n-1]=0;}return 14;}
#else
#include_next <regex.h>
#endif
