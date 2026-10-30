# -*- coding: utf-8 -*-
from __future__ import print_function
import os,sys,unittest
sys.path.insert(0,os.path.abspath(os.path.join(os.path.dirname(__file__),'..')))
from src.epgcore import reconcile_iptv_services, build_service_entry


def item(ref,name):
    return build_service_entry(ref,name)


class ReconcileTests(unittest.TestCase):
    def test_stale_memory_and_encoded_url_are_collapsed(self):
        disk=item('4097:0:1:3086:8C24:46C:EEE0BBD9:0:0:0:http%3a//example.org/live/a.m3u8:TVP 1 HD','TVP 1 HD')
        old=item('4097:0:1:0:0:0:0:0:0:0:http://example.org/live/a.m3u8:TVP 1 HD','TVP 1 HD')
        got,stats=reconcile_iptv_services([old],[disk])
        self.assertEqual([x['full_ref'] for x in got],[disk['full_ref']])
        self.assertEqual(stats['merged_duplicates'],1)
        self.assertEqual(stats['dvb_ref_disagreements'],1)

    def test_distinct_streams_same_name_are_preserved(self):
        a=item('4097:0:1:10:20:30:40:0:0:0:http%3a//example.com/one.m3u8:TVP 1','TVP 1')
        b=item('4097:0:1:11:21:31:41:0:0:0:http%3a//example.com/two.m3u8:TVP 1','TVP 1')
        got,stats=reconcile_iptv_services([a],[b])
        self.assertEqual(len(got),2)
        self.assertEqual(stats['memory_only'],1)

    def test_separate_service_types_not_collapsed(self):
        a=item('5001:0:1:10:20:30:40:0:0:0:http%3a//example.com/one.m3u8:TVP 1','TVP 1')
        b=item('4097:0:1:11:21:31:41:0:0:0:http%3a//example.com/one.m3u8:TVP 1','TVP 1')
        got,stats=reconcile_iptv_services([a],[b])
        self.assertEqual(len(got),2)

    def test_display_name_in_url_not_removed_when_different(self):
        a=item('4097:0:1:10:20:30:40:0:0:0:http%3a//example.com/one.m3u8?token=one%3a2:TVP 1','TVP 1')
        b=item('4097:0:1:11:21:31:41:0:0:0:http%3a//example.com/one.m3u8?token=one%3a2:TVP 1','TVP 1')
        got,stats=reconcile_iptv_services([a],[b])
        self.assertEqual(len(got),1)

    def test_empty_disk_retains_memory(self):
        a=item('4097:0:1:0:0:0:0:0:0:0:http%3a//example.net/live/a.m3u8:Station','Station')
        got,stats=reconcile_iptv_services([a],[])
        self.assertEqual(got,[a])
        self.assertEqual(stats['on_disk'],0)

    def test_bytewise_identical_refs_not_duplicated(self):
        a=item('4097:0:1:1:2:3:4:0:0:0:http%3a//example.net/live/a.m3u8:Station','Station')
        got,stats=reconcile_iptv_services([a,a],[a,a])
        self.assertEqual(len(got),1)
        self.assertEqual(stats['merged_duplicates'],0)

if __name__=='__main__':unittest.main()
