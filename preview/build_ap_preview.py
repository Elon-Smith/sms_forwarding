#!/usr/bin/env python3
"""生成配网页本地预览，仅模拟扫描、名称保存与连接，不访问真实设备。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/ui-preview/ap-preview.html"
MOCK = """<script>
// 预览数据只存在于当前页面，刷新即可重置。
var previewHost='sms',previewConnected=false;
window.fetch=async function(url,options){
  var data;
  if(url.indexOf('/wifiscan')===0){
    data=[{ssid:'Home-WiFi',rssi:-42,enc:true},{ssid:'Office-WiFi',rssi:-58,enc:true},{ssid:'Guest',rssi:-70,enc:false}];
  }else if(url.indexOf('/wificonfig')===0){
    var fields=new URLSearchParams(options.body);
    previewHost=fields.get('mdnsHost')||previewHost;
    previewConnected=true;
    data={success:true,mdnsHost:previewHost};
  }else if(url.indexOf('/apstatus')===0){
    data={connected:previewConnected,ip:previewConnected?'192.168.1.50':'',mdnsHost:previewHost};
  }else{throw new Error('预览中不支持的请求')}
  return {ok:true,json:async function(){return data}};
};
</script>
"""
page = (ROOT / "code/web_src/ap.html").read_text(encoding="utf-8")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(page.replace("<script>", MOCK + "<script>", 1), encoding="utf-8")
print(f"AP preview: {OUT}")
