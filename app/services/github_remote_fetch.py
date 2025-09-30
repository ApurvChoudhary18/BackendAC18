# github_remote_fetch.py
import os,sys, tempfile,subprocess,shutil,base64,json,re
from typing import Optional,Dict,List,Any
import requests
GITHUB_API="https://api.github.com"
def _token_headers():
    token=os.getenv("GITHUB_TOKEN") or ""
    hdrs={"Accept":"application/vnd.github+json"}
    if token:
        hdrs["Authorization"]=f"token {token}"
    return hdrs
def repo_full_from_url(url:str)->str:
    url=url.strip()
    if url.endswith(".git"):
        url=url[:-4]
    m=re.search(r"github\.com[:/]+([^/]+/[^/]+)",url)
    if not m:
        raise ValueError("invalid github url")
    return m.group(1)
def list_repo_tree(repo_url:str, branch:Optional[str]=None)->List[Dict[str,Any]]:
    repo_full=repo_full_from_url(repo_url)
    if not branch:
        r=requests.get(f"{GITHUB_API}/repos/{repo_full}",headers=_token_headers(),timeout=15)
        r.raise_for_status()
        branch=r.json().get("default_branch","main")
    r=requests.get(f"{GITHUB_API}/repos/{repo_full}/git/trees/{branch}?recursive=1",headers=_token_headers(),timeout=30)
    if r.status_code==200:
        data=r.json()
        return data.get("tree",[])
    r.raise_for_status()
def get_file_via_api(repo_url:str,path:str,ref:Optional[str]=None)->Dict[str,Any]:
    repo_full=repo_full_from_url(repo_url)
    params={}
    if ref:
        params["ref"]=ref
    r=requests.get(f"{GITHUB_API}/repos/{repo_full}/contents/{path}",headers=_token_headers(),params=params,timeout=20)
    if r.status_code==200:
        data=r.json()
        content=""
        if data.get("encoding")=="base64" and data.get("content"):
            content=base64.b64decode(data["content"]).decode("utf-8",errors="ignore")
        else:
            content=data.get("content","")
        return {"path":path,"sha":data.get("sha"),"content":content,"raw":data}
    if r.status_code==404:
        raise FileNotFoundError(f"{path} not found in {repo_full} ref={ref}")
    r.raise_for_status()
def clone_and_read(repo_url:str,path:str,branch:Optional[str]=None)->Dict[str,Any]:
    td=tempfile.mkdtemp(prefix="ghclone_")
    try:
        cmd=["git","clone","--depth","1"]
        if branch:
            cmd+=["--branch",branch]
        cmd+=[repo_url,td]
        subprocess.check_call(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        fp=os.path.join(td,path)
        if not os.path.exists(fp):
            raise FileNotFoundError(path)
        with open(fp,"r",encoding="utf-8",errors="ignore") as f:
            content=f.read()
        return {"path":path,"content":content,"sha":None,"raw":None}
    finally:
        shutil.rmtree(td,ignore_errors=True)
def fetch_file(repo_url:str,path:str,branch:Optional[str]=None)->Dict[str,Any]:
    try:
        return get_file_via_api(repo_url,path,ref=branch)
    except Exception:
        return clone_and_read(repo_url,path,branch)
def fetch_candidates_under_services(repo_url:str,branch:Optional[str]=None)->List[str]:
    tree=list_repo_tree(repo_url,branch=branch)
    paths=[t["path"] for t in tree if t.get("path","").startswith("backend/app/services/")]
    return paths
if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("repo_url")
    p.add_argument("--list-services",action="store_true")
    p.add_argument("--path")
    p.add_argument("--branch")
    args=p.parse_args()
    if args.list_services:
        tr=fetch_candidates_under_services(args.repo_url,branch=args.branch)
        print(json.dumps(tr,indent=2))
        sys.exit(0)
    if not args.path:
        print("specify --path or use --list-services")
        sys.exit(1)
    f=fetch_file(args.repo_url,args.path,branch=args.branch)
    print(json.dumps({"path":f.get("path"),"sha":f.get("sha"),"len":len(f.get("content",""))},indent=2))
