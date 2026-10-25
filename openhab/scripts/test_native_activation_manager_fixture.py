"""Private file-backed manager double used by independent recovery processes."""
from pathlib import Path
import json,os,sys,time
from hashlib import sha256
import household_native_lifecycle as life
import household_native_family as family
import household_native_install as install
import household_cycle_deploy as deploy


def configure(root):
    life.verify_manager_domain=lambda data:{'private_process_double':True}
    def timer(unit):return life.read(root/'timers.json')[unit]
    def systemctl(action,unit=None):
        if action=='daemon-reload':return ''
        assert action in ('stop','start') and unit in life.TIMERS
        rows=life.read(root/'timers.json');row=rows[unit];row['ActiveState']='inactive' if action=='stop' else 'active'
        row['InactiveEnterTimestampMonotonic']=str(int(row['InactiveEnterTimestampMonotonic'])+1)
        life.save(root/'timers.json',rows);return ''
    def verified(path,guard):
        guard();return {'deployment_sha256':'a'*64}
    def effective(path,guard):
        guard()
        assert life._matches(life._targets(root/'units',path))
        assert all(timer(u)['ActiveState']=='inactive' for u in life.TIMERS)
        return {'status':'native_effective_family_verified'}
    life._timer=timer;deploy._systemctl=systemctl;family.verify=verified;install._verify_effective_family=effective


def main():
    root=Path(sys.argv[1]);configure(root)
    if sys.argv[2]=='watch':life.watch(root/'reservation')
    else:life.recover(root/'reservation')


if __name__=='__main__':main()
