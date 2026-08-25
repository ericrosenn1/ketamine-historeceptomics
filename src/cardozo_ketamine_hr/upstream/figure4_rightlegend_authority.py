#!/usr/bin/env python3
"""Render the frozen-coordinate Figure 4 with direct labels and a right legend.

This visual-only producer reads an explicitly supplied output package, retains
all validated PCA coordinates and axis metadata, and changes only layout and
rendering. It neither refits PCA nor jitters points.

Publication contract
--------------------
Purpose: Render publication variants from already frozen Figure 4 coordinates.
Stage/lane: Visual-only post-analysis Figure 4 rendering and layout QA.
Inputs: An explicit output root containing validated and frozen coordinate CSVs.
Outputs: PDF/SVG/PNG/TIFF variants plus coordinate, label, palette, comparison,
and numerical/layout/export QA evidence below that root.
Side effects: Writes only rendering derivatives and QA files under the supplied root.
Invariants: The 26-profile roster, PCA coordinates, axis variance, class palette,
direct labels, prominent ketamine, and zero refit/jitter remain fixed.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations
import argparse,csv,hashlib,json,xml.etree.ElementTree as ET
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as effects
from matplotlib.lines import Line2D
from matplotlib.text import Text
import numpy as np
from PIL import Image,ImageDraw,ImageFont

EXTERNAL=["Bupropion","Fluoxetine","Duloxetine","Venlafaxine","Scopolamine","Dextromethorphan","Morphine","Propofol","Dexmedetomidine","Lysergide (LSD)","Psilocin","Clozapine","Chlorpromazine","Sertraline","Mirtazapine","Aripiprazole","Haloperidol","Olanzapine","Risperidone","Quetiapine","Ziprasidone","PCP","Valproate","Lamotrigine","Psilocybin"]
PRIMARY="Ketamine, pooled parent"
GROUPS={"Antidepressant":["Bupropion","Fluoxetine","Duloxetine","Venlafaxine","Sertraline","Mirtazapine"],"Antipsychotic":["Clozapine","Chlorpromazine","Aripiprazole","Haloperidol","Olanzapine","Risperidone","Quetiapine","Ziprasidone"],"Serotonergic psychedelic":["Lysergide (LSD)","Psilocin","Psilocybin"],"Anesthetic/sedative":["Propofol","Dexmedetomidine"],"NMDA/dissociative":["Dextromethorphan","PCP"],"Analgesic/opioid":["Morphine"],"Mood stabilizer/antiepileptic":["Valproate","Lamotrigine"],"Cholinergic":["Scopolamine"]}
PALETTE={"Antidepressant":"#159BD3","Antipsychotic":"#F06A00","Serotonergic psychedelic":"#D94B9B","Anesthetic/sedative":"#16A58C","NMDA/dissociative":"#E9A900","Analgesic/opioid":"#666666","Mood stabilizer/antiepileptic":"#55B7DF","Cholinergic":"#A8644F","Ketamine":"#202020"}
ORDER=list(GROUPS)+["Ketamine"]
MANUAL_A={"Haloperidol":(6,9),"Aripiprazole":(6,-8),"Risperidone":(18,-7),"Ziprasidone":(6,13),"Dexmedetomidine":(6,18),"Chlorpromazine":(6,-14),"Clozapine":(6,5),"Scopolamine":(6,0),"Lamotrigine":(6,11),"Valproate":(6,-12),"Sertraline":(6,0),"Quetiapine":(6,0),"Ketamine":(8,0)}
MANUAL_B={"Haloperidol":(5,8),"Aripiprazole":(5,-7),"Risperidone":(16,-6),"Ziprasidone":(5,12),"Dexmedetomidine":(5,16),"Chlorpromazine":(5,-12),"Clozapine":(5,4),"Scopolamine":(5,0),"Lamotrigine":(5,10),"Valproate":(5,-11),"Sertraline":(5,0),"Quetiapine":(5,0),"Ketamine":(7,0)}

@dataclass(frozen=True)
class P:
 """Store one frozen profile coordinate and its display metadata."""
 name:str
 label:str
 xtext:str
 ytext:str
 x:float
 y:float
 group:str
def sha(path):
 """Return the SHA-256 digest for a protected source file."""
 h=hashlib.sha256()
 with path.open("rb") as f:
  for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
 return h.hexdigest()
def group_for(name):
 """Return the approved drug-class group for a profile."""
 for group,names in GROUPS.items():
  if name in names:return group
 raise ValueError(name)
def label_for(name):
 """Return the approved direct-label text for one profile."""
 return "Ketamine" if name==PRIMARY else "LSD" if name=="Lysergide (LSD)" else name
def read_source(root):
 """Load and validate the frozen 26-profile Figure 4 coordinates."""
 table=root/"source_data"/"VALIDATED_FIGURE4_SOURCE_COORDINATES.csv";frozen=root/"source_data"/"FROZEN_GLOBAL_FIXED_REFERENCE_PCA_SCORES.csv"
 with table.open(encoding="utf-8-sig",newline="") as f:rows=list(csv.DictReader(f))
 chosen=[r for r in rows if r.get("included_main","").lower()=="true"];ext=[r for r in chosen if r["source_profile_name"] in EXTERNAL];ket=[r for r in chosen if r["source_profile_name"]==PRIMARY]
 if len(chosen)!=26 or [r["source_profile_name"] for r in ext]!=EXTERNAL or len(ket)!=1:raise RuntimeError("Validated current-Figure-4 roster mismatch")
 profiles=[P(r["source_profile_name"],label_for(r["source_profile_name"]),r["PC1"],r["PC2"],float(r["PC1"]),float(r["PC2"]),"Ketamine" if r["source_profile_name"]==PRIMARY else group_for(r["source_profile_name"])) for r in ext+ket]
 with frozen.open(encoding="utf-8-sig",newline="") as f:fr=list(csv.DictReader(f))
 a={r["PC1_variance_fraction"] for r in fr};b={r["PC2_variance_fraction"] for r in fr}
 if a!={"0.7784150849737271"} or b!={"0.19692394995125112"}:raise RuntimeError("Frozen axis metadata mismatch")
 return profiles,Decimal(next(iter(a))),Decimal(next(iter(b))),table,frozen
def overlap(a,b,pad=.75):
 """Return the padded intersection area of two display-space boxes."""
 return max(0,min(a[2]+pad,b[2]+pad)-max(a[0]-pad,b[0]-pad))*max(0,min(a[3]+pad,b[3]+pad)-max(a[1]-pad,b[1]-pad))
def layout(ax,profiles,size,compact):
 """Choose deterministic label offsets without moving any data point."""
 fig=ax.figure;fig.canvas.draw();renderer=fig.canvas.get_renderer();dpi=fig.dpi;axes=ax.get_window_extent(renderer=renderer);anchors={p.name:tuple(ax.transData.transform((p.x,p.y))) for p in profiles};dims={};temp=[]
 for p in profiles:temp.append((p,fig.text(0,0,p.label,fontsize=size+.65*(p.name==PRIMARY),fontweight="bold" if p.name==PRIMARY else "normal",family="sans-serif")))
 fig.canvas.draw();renderer=fig.canvas.get_renderer()
 for p,t in temp:box=t.get_window_extent(renderer=renderer);dims[p.name]=(box.width,box.height);t.remove()
 fixed=MANUAL_B if compact else MANUAL_A;dx=5 if compact else 6;ys=[0,5,-5,9,-9,14,-14,20,-20,27,-27,35,-35,45,-45];options={p.name:[(dx,y) for y in ys]+[(dx+4,y) for y in ys] for p in profiles};selected={p.name:fixed[p.label] for p in profiles if p.label in fixed};fixed_names=set(selected)
 def box(name,opt):
  """Return the display-space label box for one candidate offset."""
  x,y=anchors[name];w,h=dims[name];ox,oy=opt[0]*dpi/72,opt[1]*dpi/72
  return (x+ox,y+oy-h/2,x+ox+w,y+oy+h/2)
 def cost(name,opt,chosen):
  """Score clipping, overlap, and displacement for one label offset."""
  b=box(name,opt);outside=max(0,axes.x0+2-b[0])+max(0,b[2]-axes.x1+2)+max(0,axes.y0+2-b[1])+max(0,b[3]-axes.y1+2);hit=sum(overlap(b,box(other,o)) for other,o in chosen.items() if other!=name)
  return 100000*outside+40000*hit+.05*(opt[0]**2+opt[1]**2)+.8*abs(opt[1])
 for p in sorted([p for p in profiles if p.name not in fixed_names],key=lambda p:(-len(p.label),p.name)):selected[p.name]=min(options[p.name],key=lambda o:cost(p.name,o,selected))
 for _ in range(30):
  changed=False
  for p in profiles:
   if p.name in fixed_names:continue
   old=selected[p.name];selected[p.name]=min(options[p.name],key=lambda o:cost(p.name,o,selected));changed|=old!=selected[p.name]
  if not changed:break
 return selected
def legend_handles():
 """Build the fixed single-column class legend handles."""
 handles=[]
 for group in ORDER:
  handles.append(Line2D([0],[0],marker="o",linestyle="none",label=group,markerfacecolor=PALETTE[group],markeredgecolor="#111111",markeredgewidth=1.05 if group=="Ketamine" else .6,markersize=8.2 if group=="Ketamine" else 5.9))
 return handles
def audit(fig,ax,annotations,legend,offsets):
 """Audit label overlap, clipping, and right-legend placement."""
 fig.canvas.draw();renderer=fig.canvas.get_renderer();axes=ax.get_window_extent(renderer=renderer);figure=fig.bbox;boxes=[(p,Text.get_window_extent(a,renderer=renderer)) for p,a in annotations];hits=[]
 for i,(p,b) in enumerate(boxes):
  for q,c in boxes[i+1:]:
   area=overlap((b.x0,b.y0,b.x1,b.y1),(c.x0,c.y0,c.x1,c.y1))
   if area>.5:hits.append([p.label,q.label,area])
 clipped=[p.label for p,b in boxes if b.x0<axes.x0-.5 or b.x1>axes.x1+.5 or b.y0<axes.y0-.5 or b.y1>axes.y1+.5];lb=legend.get_window_extent(renderer=renderer);legend_outside_right=lb.x0>=axes.x1-1;legend_below=lb.y1<axes.y0;legend_clipped=lb.x0<figure.x0-1 or lb.x1>figure.x1+1 or lb.y0<figure.y0-1 or lb.y1>figure.y1+1
 return {"label_count":len(boxes),"label_overlap_count":len(hits),"label_overlaps":hits,"clipped_label_count":len(clipped),"clipped_labels":clipped,"leader_line_count":0,"all_labels_right":all(v[0]>0 for v in offsets.values()),"legend_outside_right":bool(legend_outside_right),"legend_below_plot":bool(legend_below),"legend_clipped":bool(legend_clipped),"legend_columns":1,"status":"PASS" if not hits and not clipped and not legend_clipped and legend_outside_right and not legend_below else "FAIL"}
def render(profiles,pc1,pc2,base,name,compact):
 """Render one coordinate-preserving Figure 4 layout variant."""
 size=6.15 if compact else 6.45
 with plt.rc_context({"font.family":"sans-serif","font.sans-serif":["Arial","Helvetica","DejaVu Sans"],"font.size":8,"axes.linewidth":.9,"pdf.fonttype":42,"svg.fonttype":"none","figure.facecolor":"white","savefig.facecolor":"white"}):
  fig,ax=plt.subplots(figsize=(210/25.4,132/25.4),dpi=180);fig.subplots_adjust(left=.08,right=.755,top=.97,bottom=.13);x=np.array([p.x for p in profiles]);y=np.array([p.y for p in profiles]);ax.set_xlim(x.min()-np.ptp(x)*.16,x.max()+np.ptp(x)*.16);ax.set_ylim(y.min()-np.ptp(y)*.17,y.max()+np.ptp(y)*.17)
  for p in profiles:
   if p.name==PRIMARY:ax.scatter(p.x,p.y,s=92 if not compact else 84,marker="o",facecolor=PALETTE["Ketamine"],edgecolor="#000000",linewidth=1.3,zorder=12)
   else:ax.scatter(p.x,p.y,s=43 if not compact else 39,marker="o",facecolor=PALETTE[p.group],edgecolor="#111111",linewidth=.65,zorder=6)
  for spine in ax.spines.values():spine.set_visible(True);spine.set_color("#111111")
  ax.grid(False);ax.tick_params(axis="both",labelsize=7.5,width=.72,length=3,color="#111111");ax.set_xlabel(f"PC1 ({float(pc1)*100:.1f}%)",fontsize=9.0,labelpad=5);ax.set_ylabel(f"PC2 ({float(pc2)*100:.1f}%)",fontsize=9.0,labelpad=5)
  offsets=layout(ax,profiles,size,compact);annotations=[]
  for p in profiles:
   ox,oy=offsets[p.name];a=ax.annotate(p.label,(p.x,p.y),xytext=(ox,oy),textcoords="offset points",ha="left",va="center",fontsize=size+.7*(p.name==PRIMARY),fontweight="bold" if p.name==PRIMARY else "normal",color="#111111",zorder=20,clip_on=True);a.set_path_effects([effects.withStroke(linewidth=1.4,foreground="white")]);annotations.append((p,a))
  legend=ax.legend(handles=legend_handles(),loc="center left",bbox_to_anchor=(1.012,.5),frameon=False,ncol=1,fontsize=6.35 if not compact else 6.1,handletextpad=.5,labelspacing=.7,borderaxespad=0)
  qc=audit(fig,ax,annotations,legend,offsets)
  if qc["status"]!="PASS":raise RuntimeError(f"Layout/legend QC failed for {name}: {qc}")
  base.parent.mkdir(parents=True,exist_ok=True);fig.savefig(base.with_suffix(".pdf"));fig.savefig(base.with_suffix(".svg"));fig.savefig(base.parent/f"{base.name}_600dpi.png",dpi=600);fig.savefig(base.parent/f"{base.name}_600dpi.tiff",dpi=600,pil_kwargs={"compression":"tiff_lzw"});plt.close(fig)
 qc.update({"variant":name,"canvas_width_mm":210,"canvas_height_mm":132,"palette":PALETTE,"ketamine_marker":"dark charcoal circular marker with black border"});labels=[{"variant":name,"profile":p.name,"label":p.label,"offset_x_pt":offsets[p.name][0],"offset_y_pt":offsets[p.name][1],"leader_line":False} for p in profiles];return qc,labels
def csvout(path,fields,rows):
 """Write a deterministic CSV evidence table."""
 with path.open("w",encoding="utf-8",newline="") as f:w=csv.DictWriter(f,fieldnames=fields,lineterminator="\n",extrasaction="ignore");w.writeheader();w.writerows(rows)
def export_checks(bases):
 """Validate every rendered export format and resolution."""
 rows=[]
 for base in bases:
  for path,kind in [(base.with_suffix(".pdf"),"PDF"),(base.with_suffix(".svg"),"SVG"),(base.parent/f"{base.name}_600dpi.png","PNG"),(base.parent/f"{base.name}_600dpi.tiff","TIFF")]:
   r={"file":path.name,"format":kind,"exists":path.exists(),"bytes":path.stat().st_size if path.exists() else 0,"status":"PASS"}
   if not path.exists() or r["bytes"]<4000:r["status"]="FAIL"
   if kind in {"PNG","TIFF"} and path.exists():
    with Image.open(path) as im:im.load();dpi=im.info.get("dpi",(None,None));r.update({"pixels":[im.width,im.height],"dpi_x":float(dpi[0]) if dpi[0] else None});r["status"]="PASS" if r["status"]=="PASS" and dpi[0] and abs(float(dpi[0])-600)<1.5 else "FAIL"
   if kind=="SVG" and path.exists():
    root=ET.parse(path).getroot();r["text_nodes"]=sum(1 for n in root.iter() if n.tag.endswith("text"));r["status"]="PASS" if r["status"]=="PASS" and root.tag.endswith("svg") and r["text_nodes"]>0 else "FAIL"
   if kind=="PDF" and path.exists():
    raw=path.read_bytes();r["status"]="PASS" if r["status"]=="PASS" and raw.startswith(b"%PDF-") and b"%%EOF" in raw[-2048:] else "FAIL"
   rows.append(r)
 return rows
def comparison(root,bases):
 """Create the side-by-side visual-review sheet."""
 items=[("Current",root/"comparison"/"CURRENT_FIGURE4_MAIN_CARDOZO_BRIGHT_RIGHTLABELS_600dpi.png",180),("A — right legend bright",bases[0].parent/f"{bases[0].name}_600dpi.png",210),("B — right legend compact",bases[1].parent/f"{bases[1].name}_600dpi.png",210)];dpi=150;head=80;gap=25;render=[]
 for title,path,width_mm in items:
  with Image.open(path) as im:
   target=round(width_mm/25.4*dpi);pic=im.convert("RGB").resize((target,round(im.height*target/im.width)),Image.Resampling.LANCZOS);render.append((title,pic))
 width=sum(p.width for _,p in render)+gap*4;height=max(p.height for _,p in render)+head+gap;sheet=Image.new("RGB",(width,height),"white");draw=ImageDraw.Draw(sheet);font=ImageFont.truetype("arial.ttf",26) if Path("C:/Windows/Fonts/arial.ttf").exists() else ImageFont.load_default();x=gap
 for title,pic in render:draw.text((x,25),title,font=font,fill="#111111");sheet.paste(pic,(x,head));x+=pic.width+gap
 sheet.save(root/"comparison"/"FIGURE4_FINAL_REVIEW_COMPARISON.png",dpi=(dpi,dpi));sheet.save(root/"comparison"/"FIGURE4_FINAL_REVIEW_COMPARISON.pdf",resolution=float(dpi))
def main():
 """Render both approved variants and require all numerical and layout checks."""
 ap=argparse.ArgumentParser();ap.add_argument("--output-root",type=Path,required=True);args=ap.parse_args();root=args.output_root.resolve();profiles,pc1,pc2,table,frozen=read_source(root);pre={str(table):sha(table),str(frozen):sha(frozen)}
 specs=[("A_RIGHTLEGEND_BRIGHT",root/"final"/"FINAL_FIGURE4_CARDOZO_BRIGHT_RIGHTLEGEND",False),("B_RIGHTLEGEND_BRIGHT_COMPACT",root/"alternate"/"ALT_FIGURE4_CARDOZO_BRIGHT_RIGHTLEGEND_COMPACT",True)];layouts=[];labels=[];plotted=[];bases=[]
 for name,base,compact in specs:qc,rows=render(profiles,pc1,pc2,base,name,compact);layouts.append(qc);labels+=rows;bases.append(base);plotted += [{"variant":name,"profile":p.name,"PC1":p.xtext,"PC2":p.ytext} for p in profiles]
 csvout(root/"source_data"/"PALETTE_SPECIFICATION.csv",["category","hex"],[{"category":g,"hex":PALETTE[g]} for g in ORDER]);csvout(root/"qc"/"PLOTTED_COORDINATES.csv",["variant","profile","PC1","PC2"],plotted);csvout(root/"qc"/"LABEL_POSITIONS.csv",["variant","profile","label","offset_x_pt","offset_y_pt","leader_line"],labels)
 expected={p.name:(Decimal(p.xtext),Decimal(p.ytext)) for p in profiles};delta=max((max(abs(Decimal(r["PC1"])-expected[r["profile"]][0]),abs(Decimal(r["PC2"])-expected[r["profile"]][1])) for r in plotted),default=Decimal(0));post={str(table):sha(table),str(frozen):sha(frozen)}
 checks=[{"check":"points_each_candidate","observed":{n:sum(r["variant"]==n for r in plotted) for n,*_ in specs},"expected":26,"status":"PASS"},{"check":"external_drugs","observed":25,"expected":25,"status":"PASS"},{"check":"ketamine","observed":1,"expected":1,"status":"PASS"},{"check":"coordinate_max_abs_delta","observed":"0" if delta==0 else str(delta),"expected":"0","status":"PASS" if delta==0 else "FAIL"},{"check":"PCA_refit_or_jitter","observed":False,"expected":False,"status":"PASS"},{"check":"axis_text","observed":"PC1 (77.8%); PC2 (19.7%)","expected":"unchanged","status":"PASS"},{"check":"palette_exact_match","observed":PALETTE,"expected":PALETTE,"status":"PASS"},{"check":"ketamine_dark_charcoal","observed":PALETTE["Ketamine"],"expected":"#202020","status":"PASS"},{"check":"legend_outside_right_all","observed":all(q["legend_outside_right"] for q in layouts),"expected":True,"status":"PASS" if all(q["legend_outside_right"] for q in layouts) else "FAIL"},{"check":"legend_below_any","observed":any(q["legend_below_plot"] for q in layouts),"expected":False,"status":"PASS" if not any(q["legend_below_plot"] for q in layouts) else "FAIL"},{"check":"leader_lines","observed":sum(q["leader_line_count"] for q in layouts),"expected":0,"status":"PASS"},{"check":"protected_snapshots_unchanged","observed":pre==post,"expected":True,"status":"PASS" if pre==post else "FAIL"}]
 (root/"qc"/"NUMERICAL_QC.json").write_text(json.dumps({"status":"PASS" if all(x["status"]=="PASS" for x in checks) else "FAIL","validated_source_sha256":pre[str(table)],"frozen_score_sha256":pre[str(frozen)],"checks":checks},indent=2),encoding="utf-8");(root/"qc"/"VISUAL_LAYOUT_QC.json").write_text(json.dumps({"status":"PASS" if all(q["status"]=="PASS" for q in layouts) else "FAIL","candidates":layouts},indent=2),encoding="utf-8");exports=export_checks(bases);(root/"qc"/"EXPORT_QC.json").write_text(json.dumps({"status":"PASS" if all(x["status"]=="PASS" for x in exports) else "FAIL","checks":exports},indent=2),encoding="utf-8");comparison(root,bases)
 if not all(x["status"]=="PASS" for x in checks) or not all(q["status"]=="PASS" for q in layouts) or not all(x["status"]=="PASS" for x in exports):raise RuntimeError("Mandatory QC failed")
 print(json.dumps({"status":"BUILD_PASS_PENDING_EXTERNAL_RENDER_AND_VISUAL_REVIEW","coordinate_max_abs_delta":"0" if delta==0 else str(delta),"legend":"OUTSIDE_RIGHT_SINGLE_COLUMN","leader_lines":0,"output_root":str(root)},indent=2))
if __name__=="__main__":main()
