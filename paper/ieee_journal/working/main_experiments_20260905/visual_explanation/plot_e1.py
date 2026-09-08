from pathlib import Path
import csv,json,collections
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.ticker import PercentFormatter

OUT=Path(__file__).resolve().parent
ROOT=OUT.parent
font_manager.fontManager.addfont('/System/Library/Fonts/STHeiti Medium.ttc')
plt.rcParams.update({'font.family':font_manager.FontProperties(fname='/System/Library/Fonts/STHeiti Medium.ttc').get_name(),'font.size':11,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none','pdf.fonttype':42})
blue='#0072B2'; orange='#D55E00'; purple='#8C5C92'; green='#009E73'; grey='#6B7280'
series=[];agreements=[]
for seed in (7201,8301,9401):
    accepted=json.loads((ROOT/f'runs/24hh_seed{seed}/accepted.json').read_text())
    run=Path(accepted['run_dir']); analysis=Path(accepted['analysis'])
    rows=list(csv.DictReader((analysis/'process_metrics.csv').open()))
    series.extend([{'seed':seed,**r} for r in rows])
    es=[json.loads(l) for l in (run/'events/events.jsonl').read_text().splitlines()]
    profiles=[json.loads(l) for l in (run/'selected_profiles.jsonl').read_text().splitlines()]
    hhlabels={h['household_id']:f'H{i+1}' for i,h in enumerate(profiles)}
    cs={}
    for e in es:
        for hid,items in e['world']['household_commitments'].items():
            for cid,c in items.items():
                if len(c['party']['traveler_ids'])<2:continue
                if cid not in cs:
                    m=e['interaction']['messages'][cid.removeprefix('commit:')]
                    cs[cid]={'seed':seed,'household':hhlabels[hid],'id':cid,'proposal_step':m['issued_step'],'agreement_step':c['created_step'],'planned_departure_step':c['party']['depart_step'],'route':c['party']['route_id'],'status_changes':[]}
                rec=cs[cid]
                if not rec['status_changes'] or rec['status_changes'][-1]['status']!=c['status']:
                    rec['status_changes'].append({'step':e['step'],'status':c['status']})
                rec['final_status']=c['status']
    versions=collections.Counter()
    for r in sorted(cs.values(),key=lambda r:(int(r['household'][1:]),r['proposal_step'])):
        versions[r['household']]+=1;r['version']=versions[r['household']];agreements.append(r)
with (OUT/'source_curves.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=list(series[0]));w.writeheader();w.writerows(series)
(OUT/'source_agreements.json').write_text(json.dumps(agreements,ensure_ascii=False,indent=2)+'\n')

def decorate(ax):
    ax.set_xlim(0,25)
    ax.set_xticks([0,3,7,9,12,15,20,25])
    ax.grid(axis='y',color='#e8eaed',lw=.8)
    for x,c in [(3,blue),(7,purple),(9,orange)]:ax.axvline(x,color=c,lw=1.1,ls=':',zorder=0)
    ax.axvspan(9,25,color=orange,alpha=.035,zorder=0)

def event_strip(ax):
    ax.set_xlim(0,25);ax.set_ylim(0,1);ax.axis('off')
    ax.plot([0,25],[.13,.13],color='#a0a5ab',lw=1)
    for step,c,text,tx in [(3,blue,'第 3 步\n发布建议撤离',2.5),(7,purple,'第 7 步\n发布强制撤离',6.7),(9,orange,'第 9 步\n主路关闭',10.5)]:
        ax.plot(step,.13,'o',color=c,ms=5)
        ax.annotate(text,xy=(step,.13),xytext=(tx,.98),ha='center',va='top',fontsize=11,color=c,arrowprops={'arrowstyle':'-','color':c,'lw':.9})
    ax.text(19,.68,'外部事件按固定时间发生\n居民收到信息的时间另行记录',ha='center',va='center',fontsize=10,color=grey)

def draw_curve(ax,key,label,color,ls):
    arrays=np.array([[0]+[float(r[key]) for r in series if r['seed']==seed] for seed in (7201,8301,9401)])
    x=np.arange(26);mean=arrays.mean(axis=0)
    ax.fill_between(x,arrays.min(axis=0),arrays.max(axis=0),step='post',color=color,alpha=.12,lw=0)
    ax.step(x,mean,where='post',color=color,lw=2.5,ls=ls,label=label)
    ax.plot(25,mean[-1],marker='o',color=color,ms=4,clip_on=False)
    return mean

fig=plt.figure(figsize=(11,8.4));gs=fig.add_gridspec(3,1,height_ratios=[.72,2.15,2.15],left=.105,right=.97,top=.87,bottom=.20,hspace=.48)
fig.suptitle('主实验：信息、协商与实际行动怎样随事件推进？',x=.105,ha='left',y=.973,fontsize=17,fontweight='bold')
fig.text(.105,.923,'24 户 · 3 次完整运行 · 25 步观察窗口',fontsize=11,color=grey)
event_strip(fig.add_subplot(gs[0]))
ax=fig.add_subplot(gs[1]);decorate(ax)
draw_curve(ax,'official_recipient_share','已收到官方信息',blue,'--')
draw_curve(ax,'first_departure_share','已实际首次出发',green,'-')
ax.set_title('(a) 信息送达与出发时间',loc='left',fontsize=12,fontweight='bold',pad=12)
ax.set_ylim(0,1);ax.yaxis.set_major_formatter(PercentFormatter(1));ax.set_ylabel('决策成员比例\n（每次 31 人）')
ax.legend(loc='upper left',ncol=2,frameon=False,fontsize=10)
ax=fig.add_subplot(gs[2]);decorate(ax)
draw_curve(ax,'joint_agreement_household_share','达成过多人约定',purple,'--')
draw_curve(ax,'joint_execution_household_share','实际共同出发',orange,'-')
ax.set_title('(b) 约定形成与共同执行',loc='left',fontsize=12,fontweight='bold',pad=12)
ax.set_ylim(0,1);ax.yaxis.set_major_formatter(PercentFormatter(1));ax.set_ylabel('多人决策家庭比例\n（每次 7 户）');ax.set_xlabel('时间步（每步 30 分钟）')
ax.legend(loc='upper left',ncol=2,frameon=False,fontsize=10)
fig.text(.105,.065,'实线／虚线为 3 次运行均值，阴影为最小—最大范围，不是置信区间。\n图示生成的行为过程；比例高低本身不代表方法优劣。官方信息送达不等于全部渠道知晓。',fontsize=10,color='#444',linespacing=1.6)
for ext in ('png','pdf','svg'):fig.savefig(OUT/f'e1_event_response.{ext}',dpi=190,facecolor='white')
plt.close(fig)

# Every formed multi-person agreement is included, including late plans.
fig=plt.figure(figsize=(12,9));gs=fig.add_gridspec(2,1,height_ratios=[.8,6.4],left=.19,right=.76,top=.88,bottom=.25,hspace=.16)
fig.suptitle('家庭约定后来怎样了？',x=.08,ha='left',y=.973,fontsize=18,fontweight='bold')
fig.text(.08,.928,'全部 12 个有效多人约定版本 · 包括取消、受阻和窗口结束尚未执行的安排',fontsize=11,color=grey)
event_strip(fig.add_subplot(gs[0]));ax=fig.add_subplot(gs[1]);decorate(ax)
markers={'executed':('s',green,'已共同出发'),'rejected':('X',orange,'封路拒绝'),'cancelled':('x',grey,'已取消'),'accepted':('>',purple,'窗口结束仍待执行')}
for i,r in enumerate(agreements):
    y=len(agreements)-1-i;start=r['proposal_step'];accept=r['agreement_step'];final=r['final_status'];end=r['status_changes'][-1]['step'] if final!='accepted' else 25
    ax.plot([start,end],[y,y],color='#b6bbc3',lw=2,zorder=2)
    ax.scatter([start],[y],s=36,facecolors='white',edgecolors=blue,linewidth=1.3,zorder=4)
    ax.scatter([accept],[y],s=33,color=blue,marker='D',zorder=5)
    marker,color,label=markers[final];ax.scatter([end],[y],s=72,color=color,marker=marker,zorder=6,clip_on=False)
    if final=='executed':label+=' · '+('备用路' if 'alternate' in r['route'] else '主路')
    if final=='accepted':label='计划第 26 步出发\n观察在第 25 步结束'
    ax.text(26,y,label,color=color,va='center',fontsize=10,clip_on=False)
    r['observed_terminal_step']=end
    if i<len(agreements)-1 and r['seed']!=agreements[i+1]['seed']:ax.axhline(y-.5,color='#b5b9bf',lw=1)
ax.set_yticks(range(len(agreements)))
ax.set_yticklabels([f"{r['seed']} · {r['household']} · 安排 {r['version']}" for r in reversed(agreements)],fontsize=10)
ax.set_ylim(-.7,len(agreements)-.3);ax.set_xlabel('时间步（每步 30 分钟）');ax.grid(False)
handles=[Line2D([],[],marker='o',mfc='white',mec=blue,color='none',label='提出安排'),Line2D([],[],marker='D',color='none',mfc=blue,mec=blue,label='明确同意'),*[Line2D([],[],marker=m,color='none',mfc=c,mec=c,label=l) for m,c,l in markers.values()]]
fig.legend(handles=handles,loc='lower left',bbox_to_anchor=(.075,.11),ncol=3,frameon=False,fontsize=10,columnspacing=2)
fig.text(.08,.047,'每行是一版约定，同一家庭可重新提出多版；这不是 12 个独立家庭。\n两版安排计划在观察窗口之后出发，不能记作执行失败。时间线只展示实际记录，未填补未观察到的后续。',fontsize=10,color='#444',linespacing=1.6)
for ext in ('png','pdf','svg'):fig.savefig(OUT/f'e1_all_agreements.{ext}',dpi=190,facecolor='white')
plt.close(fig)
print(json.dumps({'runs':3,'agreements':len(agreements),'final_statuses':dict(collections.Counter(r['final_status'] for r in agreements)),'output':str(OUT)},ensure_ascii=False))
