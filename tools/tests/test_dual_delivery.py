import copy, hashlib, importlib.util, struct, unittest
from pathlib import Path
TOOLS=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,TOOLS/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
package=module('package_candidate');soak=module('soak_dual')

class DeliveryTest(unittest.TestCase):
    def test_image_checksum_and_digest(self):
        image=bytearray(24); image[0]=0xe9; image[1]=1; image[23]=1
        struct.pack_into('<H',image,12,5)
        image.extend(struct.pack('<II',0x42000000,4)+b'abcd')
        checksum=0xef
        for v in b'abcd': checksum ^= v
        image.extend(bytes(15-len(image)%16)); image.append(checksum)
        image.extend(hashlib.sha256(image).digest())
        package.verify_esp_image(image)
        for offset in (0,1,12,23,28,32,47,48):
            bad=image.copy(); bad[offset]^=0xff
            with self.assertRaises(ValueError):package.verify_esp_image(bad)
        with self.assertRaises(ValueError):package.verify_esp_image(image[:-1])

    def test_image_gate(self):
        image=bytearray(288);image[0]=0xe9;struct.pack_into('<H',image,12,5);struct.pack_into('<I',image,32,0xabcd5432)
        for offset,text in [(48,b'1.1.7-dual.2-idf555'),(80,b'sms_forwarding_dual'),(144,b'v5.5.5')]:image[offset:offset+len(text)]=text
        self.assertEqual(package.image_identity(image)['project'],'sms_forwarding_dual')
        for offset,text in [(80,b'sms_forwarding_idf'),(48,b'1.1.7'),(144,b'v6.0.2'),(144,b'v5.5.50'),(144,b'v5.5.5-unknown')]:
            bad=image.copy();bad[offset:offset+32]=text.ljust(32,b'\0')
            with self.assertRaises(ValueError):package.image_identity(bad)
        with self.assertRaises(ValueError):package.image_identity(bytes(100))

    def samples(self):
        return [{'at':i*60,'status':{'uptime':i*60+100,'freeHeap':100000,'version':'1.1.7-dual.2-idf555','firmwareElfSha256':'abc',
                 'modems':[{'sim':1,'uartErrors':0},{'sim':2,'uartErrors':0}]}} for i in range(721)]

    def test_soak_boundaries(self):
        rows=self.samples();self.assertTrue(soak.analyse(rows)['sample_checks_pass'])
        self.assertFalse(soak.analyse(rows)['hardware_acceptance'])
        for change in ['reboot','overflow','gap','heap','image','http']:
            bad=copy.deepcopy(rows)
            if change=='reboot':bad[300]['status']['uptime']=0
            if change=='overflow':bad[300]['status']['modems'][1]['uartErrors']=1
            if change=='gap':del bad[300]
            if change=='heap':
                for i,r in enumerate(bad):r['status']['freeHeap']-=i*20
            if change=='image':bad[300]['status']['firmwareElfSha256']='different'
            if change=='http':bad[300]={'at':18000,'error':'TimeoutError'}
            self.assertFalse(soak.analyse(bad)['sample_checks_pass'],change)

if __name__=='__main__':unittest.main()
