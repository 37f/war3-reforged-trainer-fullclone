"""No game access. Contract and caller-side validation tests."""
import ctypes as C
import json
import unittest
from pathlib import Path
from legacy_backend import Packet,LegacyTrainer,PlayerRow,UnitRow,UnitSpec,ItemRow,AbilityRow

class Contracts(unittest.TestCase):
    def test_structures(self):
        self.assertEqual(C.sizeof(Packet),7300)
        self.assertEqual(C.sizeof(PlayerRow),28);self.assertEqual(C.sizeof(UnitRow),48)
        self.assertEqual(C.sizeof(UnitSpec),1764);self.assertEqual(C.sizeof(ItemRow),24);self.assertEqual(C.sizeof(AbilityRow),12)
    def test_native_signatures(self):
        data=json.loads(Path('profile.json').read_text('utf8'))['natives']
        for name,signature in dict(GetUnitState='(Hunit;Hunitstate;)R',SetUnitState='(Hunit;Hunitstate;R)V',SetHeroStr='(Hunit;IB)V',SetHeroLevel='(Hunit;IB)V',GroupRemoveUnit='(Hgroup;Hunit;)V').items():
            self.assertEqual(data[name]['signature'],signature)
        for spec in data.values():
            self.assertEqual(len(bytes.fromhex(spec['code'])),36)
            self.assertTrue(all(0<=offset<32 for offset in spec['relocations']))
    def test_validation_stops_before_transport(self):
        t=LegacyTrainer();called=[];t._request=lambda *a,**kw:called.append((a,kw))
        for fn,args in [(t.set_resource,(0,'foo',1)),(t.set_resource,(28,'gold',1)),(t.set_resource,(0,'gold',100000001)),(t.set_hero_level,(1001,)),(t.set_hero_level,(True,)),(t.set_hero_attributes,(-1,2,3)),(t.set_hero_attributes,(2,3,100001))]:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):fn(*args)
        self.assertEqual(called,[])
    def test_default_custom_modes_are_explicit(self):
        t=LegacyTrainer();calls=[];t._request=lambda *a,**kw:calls.append((a,kw))
        t.set_hero_level(1,True);t.set_hero_attributes(2,2,2,True);t.set_hero_level(10,False)
        self.assertEqual(calls[0],((),{}))
        self.assertEqual(calls[1],((4,),dict(a=1,delta=1)))
        self.assertEqual(calls[2],((),{}))
        self.assertEqual(calls[3],((5,),dict(a=2,b=2,c=2,delta=1)))
        self.assertEqual(calls[4],((),{}))
        self.assertEqual(calls[5],((4,),dict(a=10,delta=0)))
    def test_close_unconnected_is_safe(self):
        t=LegacyTrainer();t.close();t.close();self.assertIsNone(t.mapping)
    def test_partial_operation_cannot_be_implicitly_replayed(self):
        t=LegacyTrainer();t.needs_read=True;calls=[];t._request=lambda *a,**kw:calls.append((a,kw))
        with self.assertRaises(RuntimeError):t.set_hero_level(1,True)
        with self.assertRaises(RuntimeError):t.fill_selected()
        self.assertEqual(calls,[])
    def test_clone_modes_and_fresh_selection(self):
        t=LegacyTrainer();calls=[];t._request=lambda *a,**kw:calls.append((a,kw))
        for mode,value in [('self',0),('selected',1),('player',2)]:
            t.clone_selected(3,mode,15)
            self.assertEqual(calls[-2],((),{}))
            self.assertEqual(calls[-1],((6,),dict(a=3,kind=value,target=15)))
        t.replace_selected('zhyd');self.assertEqual(calls[-1],((7,),dict(b=int.from_bytes(b'zhyd','big'))))
    def test_clone_bad_input_and_partial_lock(self):
        t=LegacyTrainer();calls=[];t._request=lambda *a,**kw:calls.append((a,kw))
        for args in [(0,), (201,), (True,), (1,'bad'), (1,'player',28)]:
            with self.assertRaises(ValueError):t.clone_selected(*args)
        for raw in ('','abc','abcde','中hyd','A!b0',123):
            with self.assertRaises(ValueError):t.replace_selected(raw)
        self.assertEqual(calls,[]);t.needs_read=True
        with self.assertRaises(RuntimeError):t.clone_selected()
        with self.assertRaises(RuntimeError):t.replace_selected()
        self.assertEqual(calls,[])

if __name__=='__main__':unittest.main()
