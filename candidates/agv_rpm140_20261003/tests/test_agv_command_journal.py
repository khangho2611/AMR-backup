"""Command outcome persistence, without hardware or control threads."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class CommandJournal(unittest.TestCase):
    def journal(self,path,**kwargs):
        spec=importlib.util.find_spec('agv_command_journal')
        self.assertIsNotNone(spec,'HTTP command responses need a retained file journal')
        from agv_command_journal import CommandOutcomeJournal
        return CommandOutcomeJournal(path,**kwargs)

    def test_written_response_survives_reopen_with_exact_blockers(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'commands.jsonl'
            journal=self.journal(path)
            response={'status':'FAILED','reason':'AUTO_NOT_READY','blockers':['NOT_ARMED','MAP_STALE']}
            result=journal.record('AUTO_START',{},422,response,{'armed':False})
            self.assertTrue(result['saved'])
            response['blockers'].clear()
            stored=json.loads(path.read_text(encoding='utf8'))
            self.assertEqual(stored['response']['blockers'],['NOT_ARMED','MAP_STALE'])
            self.assertEqual(stored['http_status'],422)
            self.assertEqual(self.journal(path).snapshot()['recent'][-1]['id'],result['id'])

    def test_history_is_bounded_and_failed_write_is_reported_truthfully(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'commands.jsonl'
            journal=self.journal(path,max_bytes=4096,capacity=3)
            for i in range(60):
                self.assertTrue(journal.record('STOP',{},422,{'reason':'STOP_UNCONFIRMED','padding':'x'*160},{})['saved'])
            snapshot=journal.snapshot()
            self.assertEqual(len(snapshot['recent']),3)
            self.assertLessEqual(path.stat().st_size,4096)
            self.assertTrue(path.with_suffix('.jsonl.1').exists())
            blocked=Path(folder)/'directory';blocked.mkdir()
            bad=self.journal(blocked)
            result=bad.record('ARM',{},422,{'reason':'NOT_READY'}, {})
            self.assertFalse(result['saved'])
            self.assertTrue(result['error'])
            self.assertFalse(bad.snapshot()['recent'][-1]['saved'])


if __name__=='__main__':unittest.main()
