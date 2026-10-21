import csv
import gzip
import hashlib
import io
import json
import subprocess

import numpy as np

from audit import replay
from runner import ROOT, load, table, write_json
from validation2 import verify_book

PRIOR=ROOT.parent/'lump17_sweep_20261021_01'
COMMIT='88bfd36584e92892aa01e3f1136da8f1cdb7f1b8'
PREFIX='research-reports/usdt_krx_live_dashboard/lump17_sweep_20261021_01'
CHECKOUT='D:/Codex_Research/archive/c_drive_migration_20261020/codex_workspace/files-pasted-by-the-user-codex/work/github-backtest-report-checkout'


def main():
    out=ROOT/'anchor_audit'
    assert not out.exists();out.mkdir(parents=True)
    v,frame,codes=load();results=[];cycles_out=[]
    rules=json.loads((PRIOR/'publish_payloads/final_500_audit_v1/best_rules.json').read_text())
    for cid,section,batch in [('L17-07-004','overall',7),('L17-01-013','min10',1)]:
        folder=PRIOR/'batches'/f'batch_{batch:04d}'/'candidates'/cid
        remote=subprocess.run(['git','-C',CHECKOUT,'show',f'{COMMIT}:{PREFIX}/batches/batch_{batch:04d}_results_v1/archive_inventory.csv','--'],capture_output=True,check=True,timeout=60).stdout
        inventory={r['path']:r for r in csv.DictReader(io.StringIO(remote.decode()))}
        for path in sorted(folder.iterdir()):
            if path.is_file():
                r=inventory[f'candidates/{cid}/{path.name}']
                assert path.stat().st_size==int(r['bytes'])
                assert hashlib.sha256(path.read_bytes()).hexdigest()==r['sha256']
        raw=np.load(folder/'numeric_result.npz');account=np.load(folder/'full_account_ledger.npz')['ledger']
        trades,events,residual,orders=raw['trades'],raw['events'],raw['residual'],raw['orders']
        legacy=replay(v,trades,events,account,orders,2.)
        independent=verify_book(v,trades,events,residual,account,orders)
        score=sum(float(t[13])/(float(t[5])*170000)*100 for t in trades)
        reference=rules[section]['result']
        assert len(trades)==reference['cycles']
        assert abs(score-reference['score_pct'])<1e-9
        assert abs(np.sum(trades[:,13])-reference['net_realized'])<.01
        assert abs(np.nanmax(account[:,:,8])-reference['mdd_krw'])<.01
        for t in trades:
            i,j=int(t[1]),int(t[3]);p=account[i:j,:,6];loss=max(0.,-float(np.nanmin(p)))
            cycles_out.append(dict(candidate_id=cid,cycle_id=int(t[17]),state='COMPLETED',entry_kst=str(frame.iloc[i]['timestamp_kst']),
                exit_kst=str(frame.iloc[j]['timestamp_kst']),direction=int(t[4]),contracts=17,hold_minutes=float(t[14]),
                net=float(t[13]),return_pct=float(t[13]/(t[5]*170000)*100),maximum_observed_loss=loss,
                maximum_observed_loss_pct=loss/(t[5]*170000)*100))
        if residual[0]:
            i=int(residual[2]);loss=max(0.,-float(np.nanmin(account[i:,:,6])))
            cycles_out.append(dict(candidate_id=cid,cycle_id=int(residual[0]),state='OPEN_AT_END',entry_kst=str(frame.iloc[i]['timestamp_kst']),
                exit_kst='',direction=int(residual[1]),contracts=17,hold_minutes=float(residual[11]),net=float(residual[10]),
                return_pct=float(residual[10]/(residual[3]*170000)*100),maximum_observed_loss=loss,
                maximum_observed_loss_pct=loss/(residual[3]*170000)*100))
        terminal_score=score+(residual[10]/(residual[3]*170000)*100 if residual[0] else 0.)
        end_before=float(account[-1,1,5]-30000000.)
        end_after=end_before-float(residual[9])
        peak=float(np.nanmax(account[:,:,5])-30000000.)
        mdd_after=max(float(np.nanmax(account[:,:,8])),max(0.,peak)-end_after)
        row=dict(candidate_id=cid,status='PASS_TWO_INDEPENDENT_REPLAYS_AND_REMOTE_SOURCE_HASH',cycles=len(trades),score_pct=score,
            net_realized=float(np.sum(trades[:,13])),mdd=float(np.nanmax(account[:,:,8])),
            residual_contracts=17 if residual[0] else 0,residual_net_after_exit_cost=float(residual[10]),
            last_spot_close=float(v[6][-1]),last_future_close=float(v[8][-1]),last_contract=codes[int(v[3][-1])-1],
            last_timestamp_kst=str(frame.iloc[-1]['timestamp_kst']),terminal_exit_cost=float(residual[9]),
            terminal_assumed_score_pct=float(terminal_score),terminal_assumed_net=float(np.sum(trades[:,13])+residual[10]),
            terminal_assumed_mdd=float(mdd_after),longest_hold_minutes=max([float(t[14]) for t in trades]+[float(residual[11])]),
            residual_hold_minutes=float(residual[11]),minimum_initial_headroom=float(legacy[1]),minimum_maintenance_headroom=float(legacy[2]),
            independent_vector_max_difference=independent['max_difference_krw'],
            fees=float(np.sum(events[:,8:10])),slippage=float(np.sum(events[:,10:12])),rule=rules[section]['rule'],
            terminal_execution='HYPOTHETICAL_LAST_CLOSE_ONLY; no following observed bar, no historical quote or size verification',borrow='UNVERIFIED_NOT_INCLUDED')
        results.append(row)
        print(json.dumps(row,ensure_ascii=False),flush=True)
    table(out/'anchor_summary.csv',[{k:v for k,v in r.items() if k!='rule'} for r in results])
    table(out/'anchor_cycles_and_open_risk.csv',cycles_out)
    write_json(out/'anchor_validation.json',dict(status='PASS',anchors=results,source_commit=COMMIT,no_trade_recalculation=True))


if __name__=='__main__':main()
