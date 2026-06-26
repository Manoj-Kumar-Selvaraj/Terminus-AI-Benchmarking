#!/usr/bin/env bash
set -Eeuo pipefail
cat > /app/src/zonectl.c <<'EOF_C'

#define _POSIX_C_SOURCE 200809L
#include <dirent.h>
#include <errno.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#define MAX_RR 512
#define MAX_TX 512
#define MAX_OP 256
#define LINE 2048

typedef struct { char name[256], type[32], value[768]; uint32_t ttl; } RR;
typedef struct { char id[128], digest[17]; } Tx;
typedef struct { uint32_t generation, serial; char snapshot[128]; RR rr[MAX_RR]; size_t nrr; Tx tx[MAX_TX]; size_t ntx; } State;
typedef struct { char kind; char name[256], type[32], value[768]; uint32_t ttl; } Op;

static void die(const char *m) { fprintf(stderr, "%s\n", m); exit(2); }
static void path(char *out, size_t n, const char *dir, const char *name) { if (snprintf(out,n,"%s/%s",dir,name) >= (int)n) die("path too long"); }
static void ensure_dir(const char *d) { if (mkdir(d,0750) && errno!=EEXIST) die("cannot create state directory"); }
static uint64_t fnv(uint64_t h, const char *s, size_t n) { for(size_t i=0;i<n;i++){ h^=(unsigned char)s[i]; h*=UINT64_C(1099511628211);} return h; }
static uint64_t fnv0(void){return UINT64_C(1469598103934665603);}
static void trim_nl(char *s){size_t n=strlen(s); while(n && (s[n-1]=='\n'||s[n-1]=='\r')) s[--n]=0;}
static bool valid_atom(const char *s){return s && *s && !strchr(s,'\t') && !strchr(s,'\n') && !strchr(s,'|');}
static void jsons(FILE *f,const char *s){fputc('"',f); for(;*s;s++){unsigned char c=*s; if(c=='"'||c=='\\'){fputc('\\',f);fputc(c,f);} else if(c<32) fprintf(f,"\\u%04x",c); else fputc(c,f);} fputc('"',f);}
static int rr_cmp(const void *a,const void *b){const RR*x=a,*y=b;int c=strcmp(x->name,y->name);return c?c:strcmp(x->type,y->type);}
static int find_rr(State*s,const char*n,const char*t){for(size_t i=0;i<s->nrr;i++)if(!strcmp(s->rr[i].name,n)&&!strcmp(s->rr[i].type,t))return(int)i;return-1;}
static int find_tx(State*s,const char*id){for(size_t i=0;i<s->ntx;i++)if(!strcmp(s->tx[i].id,id))return(int)i;return-1;}
static void set_rr(State*s,Op*o){int i=find_rr(s,o->name,o->type); if(i<0){if(s->nrr>=MAX_RR)die("too many records");i=(int)s->nrr++;} snprintf(s->rr[i].name,sizeof s->rr[i].name,"%s",o->name);snprintf(s->rr[i].type,sizeof s->rr[i].type,"%s",o->type);snprintf(s->rr[i].value,sizeof s->rr[i].value,"%s",o->value);s->rr[i].ttl=o->ttl;}
static void del_rr(State*s,Op*o){int i=find_rr(s,o->name,o->type);if(i>=0){s->rr[i]=s->rr[s->nrr-1];s->nrr--;}}
static void apply_ops(State*s,Op*ops,size_t n){for(size_t i=0;i<n;i++)if(ops[i].kind=='S')set_rr(s,&ops[i]);else del_rr(s,&ops[i]);}
static void add_tx(State*s,const char*id,const char*d){if(s->ntx>=MAX_TX)die("too many txids");snprintf(s->tx[s->ntx].id,sizeof s->tx[s->ntx].id,"%s",id);snprintf(s->tx[s->ntx].digest,sizeof s->tx[s->ntx].digest,"%s",d);s->ntx++;}

static bool parse_u32(const char*s,uint32_t*out){char*e=NULL;errno=0;unsigned long long v=strtoull(s,&e,10);if(errno||!e||*e||v>UINT32_MAX)return false;*out=(uint32_t)v;return true;}
static bool load_snapshot_file(const char*dir,const char*file,State*s){char p[1024],line[LINE];path(p,sizeof p,dir,file);FILE*f=fopen(p,"r");if(!f)return false;memset(s,0,sizeof *s);snprintf(s->snapshot,sizeof s->snapshot,"%s",file);bool g=false,se=false;while(fgets(line,sizeof line,f)){trim_nl(line);char*save=NULL,*k=strtok_r(line,"\t",&save);if(!k)continue;if(!strcmp(k,"GEN")){char*v=strtok_r(NULL,"\t",&save);uint32_t x;if(!v||!parse_u32(v,&x)){fclose(f);return false;}s->generation=x;g=true;}else if(!strcmp(k,"SERIAL")){char*v=strtok_r(NULL,"\t",&save);if(!v||!parse_u32(v,&s->serial)){fclose(f);return false;}se=true;}else if(!strcmp(k,"TX")){char*i=strtok_r(NULL,"\t",&save),*d=strtok_r(NULL,"\t",&save);if(!i||!d||strlen(d)!=16||s->ntx>=MAX_TX){fclose(f);return false;}add_tx(s,i,d);}else if(!strcmp(k,"RR")){char*n=strtok_r(NULL,"\t",&save),*t=strtok_r(NULL,"\t",&save),*ttl=strtok_r(NULL,"\t",&save),*v=strtok_r(NULL,"",&save);uint32_t tv;if(!n||!t||!ttl||!v||!parse_u32(ttl,&tv)||s->nrr>=MAX_RR){fclose(f);return false;}RR*r=&s->rr[s->nrr++];snprintf(r->name,sizeof r->name,"%s",n);snprintf(r->type,sizeof r->type,"%s",t);snprintf(r->value,sizeof r->value,"%s",v);r->ttl=tv;}else{fclose(f);return false;}}fclose(f);return g&&se;}

static bool manifest_state(const char*dir,State*s){char p[1024],line[512],file[128];uint32_t gen;path(p,sizeof p,dir,"manifest");FILE*f=fopen(p,"r");if(!f)return false;if(!fgets(line,sizeof line,f)){fclose(f);return false;}fclose(f);trim_nl(line);char*tab=strchr(line,'\t');if(!tab)return false;*tab++=0;if(!parse_u32(line,&gen)||!valid_atom(tab))return false;snprintf(file,sizeof file,"%s",tab);if(!load_snapshot_file(dir,file,s)||s->generation!=gen)return false;return true;}


static bool load_state(const char*dir,State*s){ return manifest_state(dir,s); }


static void write_snapshot_named(const char*dir,const char*file,State*s){char p[1024],tmp[1050];path(p,sizeof p,dir,file);snprintf(tmp,sizeof tmp,"%s.tmp",p);FILE*f=fopen(tmp,"w");if(!f)die("cannot write snapshot");qsort(s->rr,s->nrr,sizeof(RR),rr_cmp);fprintf(f,"GEN\t%"PRIu32"\nSERIAL\t%"PRIu32"\n",s->generation,s->serial);for(size_t i=0;i<s->ntx;i++)fprintf(f,"TX\t%s\t%s\n",s->tx[i].id,s->tx[i].digest);for(size_t i=0;i<s->nrr;i++)fprintf(f,"RR\t%s\t%s\t%"PRIu32"\t%s\n",s->rr[i].name,s->rr[i].type,s->rr[i].ttl,s->rr[i].value);if(fflush(f)||fsync(fileno(f))||fclose(f))die("cannot sync snapshot");if(rename(tmp,p))die("cannot install snapshot");}
static void write_manifest(const char*dir,State*s){char p[1024],tmp[1050];path(p,sizeof p,dir,"manifest");snprintf(tmp,sizeof tmp,"%s.tmp",p);FILE*f=fopen(tmp,"w");if(!f)die("cannot write manifest");fprintf(f,"%"PRIu32"\t%s\n",s->generation,s->snapshot);if(fflush(f)||fsync(fileno(f))||fclose(f))die("cannot sync manifest");if(rename(tmp,p))die("cannot install manifest");}
static void clear_journal(const char*dir){char p[1024],tmp[1050];path(p,sizeof p,dir,"journal.log");snprintf(tmp,sizeof tmp,"%s.tmp",p);FILE*f=fopen(tmp,"w");if(!f)die("cannot clear journal");if(fflush(f)||fsync(fileno(f))||fclose(f))die("cannot sync journal");if(rename(tmp,p))die("cannot install journal");}
static void save_active(const char*dir,State*s){write_snapshot_named(dir,s->snapshot,s);write_manifest(dir,s);}
static void report(const char*out,State*s){FILE*f=fopen(out,"w");if(!f)die("cannot write report");qsort(s->rr,s->nrr,sizeof(RR),rr_cmp);fprintf(f,"{\"generation\":%"PRIu32",\"serial\":%"PRIu32",\"record_count\":%zu,\"records\":[",s->generation,s->serial,s->nrr);for(size_t i=0;i<s->nrr;i++){if(i)fputc(',',f);fprintf(f,"{\"name\":");jsons(f,s->rr[i].name);fprintf(f,",\"type\":");jsons(f,s->rr[i].type);fprintf(f,",\"ttl\":%"PRIu32",\"value\":",s->rr[i].ttl);jsons(f,s->rr[i].value);fputc('}',f);}fprintf(f,"],\"applied_txids\":[");for(size_t i=0;i<s->ntx;i++){if(i)fputc(',',f);jsons(f,s->tx[i].id);}fprintf(f,"]}\n");fclose(f);}

static int parse_op(char*line,Op*o){char*save=NULL,*p=strtok_r(line,"|",&save),*k=strtok_r(NULL,"|",&save),*n=strtok_r(NULL,"|",&save),*t=strtok_r(NULL,"|",&save);if(!p||strcmp(p,"O")||!k||!n||!t)return 0;if(!strcmp(k,"S")){char*ttl=strtok_r(NULL,"|",&save),*v=strtok_r(NULL,"",&save);uint32_t tv;if(!ttl||!v||!parse_u32(ttl,&tv))return 0;o->kind='S';o->ttl=tv;snprintf(o->value,sizeof o->value,"%s",v);}else if(!strcmp(k,"D")){o->kind='D';o->ttl=0;o->value[0]=0;}else return 0;snprintf(o->name,sizeof o->name,"%s",n);snprintf(o->type,sizeof o->type,"%s",t);return valid_atom(o->name)&&valid_atom(o->type);}

static int recover_state(const char*dir,State*s){char p[1024];path(p,sizeof p,dir,"journal.log");FILE*f=fopen(p,"r+");if(!f){f=fopen(p,"w+");if(!f)die("cannot open journal");}char*line=NULL;size_t cap=0;ssize_t n;bool in=false;long tx_start=0,last_good=0;char txid[128]={0},digest[17]={0};uint32_t base=0,next=0;uint64_t hash=0;Op ops[MAX_OP];size_t nops=0;while(1){long row_start=ftell(f);n=getline(&line,&cap,f);if(n<0)break;bool complete=n>0&&line[n-1]=='\n';char raw[LINE];if((size_t)n>=sizeof raw){free(line);fclose(f);return 2;}memcpy(raw,line,(size_t)n+1);trim_nl(line);if(!in){if(line[0]==0){last_good=ftell(f);continue;}char tmp[LINE];snprintf(tmp,sizeof tmp,"%s",line);char*save=NULL,*b=strtok_r(tmp,"|",&save),*id=strtok_r(NULL,"|",&save),*bs=strtok_r(NULL,"|",&save),*ns=strtok_r(NULL,"|",&save),*dg=strtok_r(NULL,"|",&save);if(!complete){if(ftruncate(fileno(f),tx_start)){free(line);fclose(f);return 2;}break;}if(!b||strcmp(b,"B")||!id||!bs||!ns||!dg||strlen(dg)!=16||!parse_u32(bs,&base)||!parse_u32(ns,&next)){free(line);fclose(f);fprintf(stderr,"journal parse failed\n");return 2;}in=true;tx_start=row_start;nops=0;hash=fnv(fnv0(),raw,(size_t)n);snprintf(txid,sizeof txid,"%s",id);snprintf(digest,sizeof digest,"%s",dg);}else if(!strncmp(line,"O|",2)){if(!complete){if(ftruncate(fileno(f),tx_start)){free(line);fclose(f);return 2;}break;}if(nops>=MAX_OP){free(line);fclose(f);fprintf(stderr,"journal parse failed\n");return 2;}char tmp[LINE];snprintf(tmp,sizeof tmp,"%s",line);if(!parse_op(tmp,&ops[nops])){free(line);fclose(f);fprintf(stderr,"journal parse failed\n");return 2;}nops++;hash=fnv(hash,raw,(size_t)n);}else if(!strncmp(line,"C|",2)){if(!complete){if(ftruncate(fileno(f),tx_start)){free(line);fclose(f);return 2;}break;}char tmp[LINE];snprintf(tmp,sizeof tmp,"%s",line);char*save=NULL,*c=strtok_r(tmp,"|",&save),*id=strtok_r(NULL,"|",&save),*hs=strtok_r(NULL,"|",&save),want[17];snprintf(want,sizeof want,"%016"PRIx64,hash);if(!c||strcmp(c,"C")||!id||!hs||strcmp(id,txid)||strcmp(hs,want)){free(line);fclose(f);fprintf(stderr,"committed journal corruption\n");return 2;}int prior=find_tx(s,txid);if(prior>=0){if(strcmp(s->tx[prior].digest,digest)){free(line);fclose(f);fprintf(stderr,"transaction id conflict\n");return 2;}}else{if(base!=s->serial||next!=(uint32_t)(base+1)){free(line);fclose(f);fprintf(stderr,"serial chain mismatch\n");return 2;}apply_ops(s,ops,nops);s->serial=next;add_tx(s,txid,digest);}in=false;last_good=ftell(f);}else{if(!complete){if(ftruncate(fileno(f),tx_start)){free(line);fclose(f);return 2;}break;}free(line);fclose(f);fprintf(stderr,"journal parse failed\n");return 2;}}
if(in){if(ftruncate(fileno(f),tx_start)){free(line);fclose(f);return 2;}}
free(line);fclose(f);save_active(dir,s);clear_journal(dir);return 0;}

static void seed(const char*dir,uint32_t serial,const char*records){ensure_dir(dir);State s={0};s.generation=1;s.serial=serial;snprintf(s.snapshot,sizeof s.snapshot,"snapshot.1.tsv");if(records){FILE*f=fopen(records,"r");if(!f)die("cannot open records");char line[LINE];while(fgets(line,sizeof line,f)){trim_nl(line);if(!*line)continue;char*save=NULL,*n=strtok_r(line,"\t",&save),*t=strtok_r(NULL,"\t",&save),*ttl=strtok_r(NULL,"\t",&save),*v=strtok_r(NULL,"",&save);uint32_t tv;if(!n||!t||!ttl||!v||!parse_u32(ttl,&tv))die("bad seed record");Op o={.kind='S',.ttl=tv};snprintf(o.name,sizeof o.name,"%s",n);snprintf(o.type,sizeof o.type,"%s",t);snprintf(o.value,sizeof o.value,"%s",v);set_rr(&s,&o);}fclose(f);}save_active(dir,&s);clear_journal(dir);}
static size_t read_changes(const char*file,Op*ops,char*digest){FILE*f=fopen(file,"r");if(!f)die("cannot open changes");char line[LINE];size_t n=0;uint64_t h=fnv0();while(fgets(line,sizeof line,f)){trim_nl(line);if(!*line)continue;char canon[LINE];snprintf(canon,sizeof canon,"%s\n",line);h=fnv(h,canon,strlen(canon));char*save=NULL,*k=strtok_r(line,"\t",&save),*name=strtok_r(NULL,"\t",&save),*type=strtok_r(NULL,"\t",&save);if(!k||!name||!type||n>=MAX_OP)die("bad change row");Op*o=&ops[n++];snprintf(o->name,sizeof o->name,"%s",name);snprintf(o->type,sizeof o->type,"%s",type);if(!strcmp(k,"SET")){char*ttl=strtok_r(NULL,"\t",&save),*v=strtok_r(NULL,"",&save);uint32_t tv;if(!ttl||!v||!parse_u32(ttl,&tv))die("bad set row");o->kind='S';o->ttl=tv;snprintf(o->value,sizeof o->value,"%s",v);}else if(!strcmp(k,"DEL")){o->kind='D';}else die("bad change operation");}fclose(f);snprintf(digest,17,"%016"PRIx64,h);return n;}
static void append_tx(const char*dir,const char*id,const char*changes,const char*crash){State s;if(!load_state(dir,&s))die("invalid active state");Op ops[MAX_OP];char digest[17];size_t n=read_changes(changes,ops,digest);char p[1024];path(p,sizeof p,dir,"journal.log");FILE*f=fopen(p,"a");if(!f)die("cannot append journal");uint32_t next=s.serial+1;char row[LINE];uint64_t h=fnv0();int z=snprintf(row,sizeof row,"B|%s|%"PRIu32"|%"PRIu32"|%s\n",id,s.serial,next,digest);fwrite(row,1,(size_t)z,f);h=fnv(h,row,(size_t)z);for(size_t i=0;i<n;i++){if(ops[i].kind=='S')z=snprintf(row,sizeof row,"O|S|%s|%s|%"PRIu32"|%s\n",ops[i].name,ops[i].type,ops[i].ttl,ops[i].value);else z=snprintf(row,sizeof row,"O|D|%s|%s\n",ops[i].name,ops[i].type);fwrite(row,1,(size_t)z,f);h=fnv(h,row,(size_t)z);}char close[128];z=snprintf(close,sizeof close,"C|%s|%016"PRIx64"\n",id,h);if(crash&&!strcmp(crash,"torn_commit")){fwrite(close,1,(size_t)(z/2),f);fflush(f);fsync(fileno(f));fclose(f);exit(75);}fwrite(close,1,(size_t)z,f);fflush(f);fsync(fileno(f));fclose(f);if(crash&&!strcmp(crash,"after_commit"))exit(75);if(recover_state(dir,&s))exit(2);}

static void cleanup_orphans(const char*dir,State*s){DIR*d=opendir(dir);if(!d)return;struct dirent*e;char p[1024];while((e=readdir(d))){if(!strncmp(e->d_name,"snapshot.",9)&&strstr(e->d_name,".tsv")&&strcmp(e->d_name,s->snapshot)){path(p,sizeof p,dir,e->d_name);unlink(p);}}closedir(d);}

static void compact(const char*dir,const char*crash){State s;if(!load_state(dir,&s))die("invalid active state");if(recover_state(dir,&s))exit(2);if(!load_state(dir,&s))die("invalid recovered state");
uint32_t old=s.generation;s.generation=old+1;snprintf(s.snapshot,sizeof s.snapshot,"snapshot.%"PRIu32".tsv",s.generation);write_snapshot_named(dir,s.snapshot,&s);if(crash&&!strcmp(crash,"after_snapshot"))exit(75);write_manifest(dir,&s);if(crash&&!strcmp(crash,"after_manifest"))exit(75);char oldfile[128],oldpath[1024];snprintf(oldfile,sizeof oldfile,"snapshot.%"PRIu32".tsv",old);path(oldpath,sizeof oldpath,dir,oldfile);unlink(oldpath);
}
static const char*arg(int argc,char**argv,const char*k){for(int i=2;i+1<argc;i++)if(!strcmp(argv[i],k))return argv[i+1];return NULL;}
int main(int argc,char**argv){if(argc<2)die("usage: zonectl COMMAND");const char*cmd=argv[1],*dir=arg(argc,argv,"--state");if(!dir)die("--state required");if(!strcmp(cmd,"seed")){const char*ss=arg(argc,argv,"--serial");uint32_t serial;if(!ss||!parse_u32(ss,&serial))die("--serial required");seed(dir,serial,arg(argc,argv,"--records"));return 0;}if(!strcmp(cmd,"apply")){const char*id=arg(argc,argv,"--txid"),*ch=arg(argc,argv,"--changes");if(!id||!ch||!valid_atom(id))die("--txid and --changes required");append_tx(dir,id,ch,arg(argc,argv,"--crash"));return 0;}if(!strcmp(cmd,"recover")){State s;if(!load_state(dir,&s))die("invalid active state");int rc=recover_state(dir,&s);if(rc)return rc;const char*out=arg(argc,argv,"--out");if(!out)die("--out required");if(!load_state(dir,&s))die("invalid recovered state");cleanup_orphans(dir,&s);report(out,&s);return 0;}if(!strcmp(cmd,"query")){State s;if(!load_state(dir,&s))die("invalid active state");const char*out=arg(argc,argv,"--out");if(!out)die("--out required");report(out,&s);return 0;}if(!strcmp(cmd,"compact")){compact(dir,arg(argc,argv,"--crash"));return 0;}die("unknown command");}

EOF_C
rm -f /tmp/zonectl-*
