import copy
import unittest
from trial import CANARY, NS, verify


class VerifyTests(unittest.TestCase):
    def fixture(self):
        rows=[];events=[]
        for i,name in enumerate(['helm-live-01','helm-live-parallel-a','helm-live-parallel-b','ordinary','excluded']):
            r={'container_id':str(i)*64,'sandbox_id':'sandbox-'+str(i),'pod_uid':'uid-'+str(i),
               'name':name,'namespace':NS if i!=4 else NS+'-excluded','node':'test-node',
               'runtime':'io.containerd.runsc.v1' if i!=3 else 'io.containerd.runc.v2','exit_code':0,
               'started_at':'2026-11-06T10:00:00Z','finished_at':'2026-11-06T10:00:04Z'}
            rows.append(r)
            if i<3:
                e={k:r[v] for k,v in [('container.id','container_id'),('sandbox_id','sandbox_id'),('pod_uid','pod_uid'),('pod_name','name'),('namespace','namespace'),('node','node')]}
                e.update(body='RuntimeObservation',source='gvisor_trace',kind='container_started',identity_status='verified',identity_origin='local_cri_and_kubernetes',container_name='workload',runtime_handler='runsc',sender_reported_drops=0,wire_canary_found=False,unexpected_attribute_count=0)
                events.append(e)
        return rows,events

    def test_valid(self):
        rows,events=self.fixture()
        self.assertEqual(verify(rows,events,'',1)['identity_matches'],3)

    def test_missing_duplicate_and_unknown_exports(self):
        rows,events=self.fixture()
        for bad in [events[:-1],events+[events[0]],events+[dict(events[0],**{'container.id':'f'*64})]]:
            with self.subTest(length=len(bad)),self.assertRaises(ValueError):verify(rows,bad,'',1)

    def test_identity_and_privacy_fail_closed(self):
        rows,events=self.fixture()
        for key,value in [('pod_uid','wrong'),('runtime_handler','runc'),('wire_canary_found',True),('unexpected_attribute_count',1),('sender_reported_drops',1)]:
            bad=copy.deepcopy(events);bad[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):verify(rows,bad,'',1)
        with self.assertRaises(ValueError):verify(rows,events,CANARY,1)

    def test_control_ledger_and_overlap_required(self):
        rows,events=self.fixture()
        with self.assertRaises(ValueError):verify(rows[:-1],events,'',1)
        rows[2]['started_at']='2026-11-06T10:00:05Z';rows[2]['finished_at']='2026-11-06T10:00:09Z'
        with self.assertRaises(ValueError):verify(rows,events,'',1)


if __name__=='__main__':unittest.main()
