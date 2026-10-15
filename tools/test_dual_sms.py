#!/usr/bin/env python3
"""Run production SMS assembly, dedupe, index queue and card-reset methods twice."""
from pathlib import Path
import os, re, shlex, subprocess, tempfile
root = Path(__file__).resolve().parents[1]
s = (root/'components/idf_sms/idf_sms.cpp').read_text('utf-8')
def fun(name):
    m = re.search(r'^(?:void|bool|uint32_t|std::string|ConcatSlot&) '+name+r'\(', s, re.M)
    return s[m.start():s.index('\n}', m.end())+2]
def struct(name):
    a = s.index('struct '+name+' {')
    return s[a:s.index('\n};', a)+3]
a = s.index('static constexpr size_t MAX_PDU_HEX_CHARS')
b = s.index('struct ConcatPart', a)
parts = s[a:b] + '\n'.join(struct(n) for n in ['ConcatPart', 'ConcatSlot', 'OutgoingSmsJob', 'DecodedSms', 'ConcatDone'])
parts += '\n' + re.search(r'^struct SmsIndex[^\n]+', s, re.M).group(0)
fields = [line for line in s.splitlines() if re.match(r'^(uint8_t s_(?:nopdu|decode)_stall_rounds|std::array<|size_t s_|bool s_(?:wait_pdu|backfill_pending|call_notified|call_saw_ring)|int64_t s_wait_pdu_until_us|std::string s_(?:urc_carry|call_number)|static constexpr int64_t CONCAT_DONE_TTL_US)', line)]
functions = '\n'.join(fun(n) for n in ['hash32', 'seen_recently', 'clear_concat_slot', 'assemble_concat', 'concat_recently_done', 'record_concat_done', 'find_concat_slot', 'handle_decoded_pdu', 'enqueue_index', 'pop_index', 'reset_card_state'])
fixture = (root/'tests/host/test_dual_sms.cpp').read_text('utf-8').replace('// @parts@', parts).replace('// @fields@', '\n'.join(fields)).replace('// @functions@', functions)
with tempfile.TemporaryDirectory(prefix='dual-sms-') as tmp:
    cpp, binary = Path(tmp)/'test.cpp', Path(tmp)/'test.exe'
    cpp.write_text(fixture, 'utf-8')
    subprocess.run([*shlex.split(os.environ.get('CXX', 'c++')), '-std=c++17', '-Wall', '-Wextra', '-Werror', str(cpp), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
