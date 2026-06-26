#!/usr/bin/env bash
set -Eeuo pipefail
cat > /app/src/SignerCtl.java <<'EOF_JAVA'

import java.io.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;

public final class SignerCtl {
    static final class Req {
        String id,digest,key,status,signature,opid; long policy;
        String row(){return String.join("\t", id,digest,key,Long.toString(policy),status,signature==null?"-":signature,opid);}
        static Req parse(String s){String[]p=s.split("\\t",-1);if(p.length!=7)throw new IllegalArgumentException("bad request journal");Req r=new Req();r.id=p[0];r.digest=p[1];r.key=p[2];r.policy=Long.parseLong(p[3]);r.status=p[4];r.signature=p[5].equals("-")?null:p[5];r.opid=p[6];return r;}
    }
    static final class Locked implements AutoCloseable {
        final FileChannel ch; final FileLock lock;
        Locked(Path dir)throws Exception{Files.createDirectories(dir);ch=FileChannel.open(dir.resolve(".lock"),StandardOpenOption.CREATE,StandardOpenOption.WRITE);lock=ch.lock();}
        public void close()throws Exception{lock.release();ch.close();}
    }
    static void fail(String m){System.err.println(m);System.exit(2);}
    static String arg(String[]a,String k){for(int i=1;i+1<a.length;i++)if(a[i].equals(k))return a[i+1];return null;}
    static long longArg(String[]a,String k){String v=arg(a,k);if(v==null)fail(k+" required");try{return Long.parseLong(v);}catch(Exception e){fail("bad "+k);return 0;}}
    static Path state(String[]a){String s=arg(a,"--state");if(s==null)fail("--state required");return Path.of(s);}
    static Properties load(Path d)throws Exception{Properties p=new Properties();Path f=d.resolve("cluster.properties");if(!Files.exists(f))fail("state not initialized");try(Reader r=Files.newBufferedReader(f)){p.load(r);}return p;}
    static void save(Path d,Properties p)throws Exception{Path t=d.resolve("cluster.properties.tmp"),f=d.resolve("cluster.properties");try(Writer w=Files.newBufferedWriter(t)){p.store(w,null);}try(FileChannel c=FileChannel.open(t,StandardOpenOption.WRITE)){c.force(true);}Files.move(t,f,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);}
    static LinkedHashMap<String,Req> requests(Path d)throws Exception{LinkedHashMap<String,Req>m=new LinkedHashMap<>();Path f=d.resolve("requests.tsv");if(Files.exists(f))for(String l:Files.readAllLines(f))if(!l.isBlank()){Req r=Req.parse(l);m.put(r.id,r);}return m;}
    static void saveRequests(Path d,LinkedHashMap<String,Req>m)throws Exception{Path t=d.resolve("requests.tsv.tmp"),f=d.resolve("requests.tsv");List<String>rows=new ArrayList<>();for(Req r:m.values())rows.add(r.row());Files.write(t,rows,StandardCharsets.UTF_8);try(FileChannel c=FileChannel.open(t,StandardOpenOption.WRITE)){c.force(true);}Files.move(t,f,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);}
    static String hex(byte[]b){StringBuilder s=new StringBuilder();for(byte x:b)s.append(String.format("%02x",x));return s.toString();}
    static String sha(String s)throws Exception{return hex(MessageDigest.getInstance("SHA-256").digest(s.getBytes(StandardCharsets.UTF_8)));}
    static Map<String,String> requestFile(String f)throws Exception{Properties p=new Properties();try(Reader r=Files.newBufferedReader(Path.of(f))){p.load(r);}String id=p.getProperty("id"),payload=p.getProperty("payload");if(id==null||id.isBlank()||payload==null)fail("request requires id and payload");return Map.of("id",id,"digest",sha(payload));}
    static String token(String node,long epoch){return node+":"+epoch;}
    static void json(Path out,String body)throws Exception{Files.writeString(out,"{"+body+"}\n");}
    static String q(String s){return "\""+s.replace("\\","\\\\").replace("\"","\\\"")+"\"";}


static void acquire(Path d,Properties p,String[]a)throws Exception{String node=arg(a,"--node"),out=arg(a,"--out");long now=longArg(a,"--now");if(node==null||node.isBlank()||out==null)fail("acquire arguments required");long epoch=Long.parseLong(p.getProperty("epoch"));String owner=p.getProperty("owner","");long expires=Long.parseLong(p.getProperty("expires"));if(owner.isBlank()||now>=expires){epoch++;owner=node;expires=now+Long.parseLong(p.getProperty("lease_ms"));p.setProperty("owner",owner);p.setProperty("epoch",Long.toString(epoch));p.setProperty("expires",Long.toString(expires));save(d,p);}else if(!owner.equals(node)){fail("lease is active for another owner");}json(Path.of(out),"\"token\":"+q(token(owner,epoch))+",\"expires\":"+expires+",\"epoch\":"+epoch);}
static void renew(Path d,Properties p,String[]a)throws Exception{String node=arg(a,"--node"),tok=arg(a,"--token"),out=arg(a,"--out");long now=longArg(a,"--now");validateLease(p,node,tok,now);long expires=now+Long.parseLong(p.getProperty("lease_ms"));p.setProperty("expires",Long.toString(expires));save(d,p);if(out!=null)json(Path.of(out),"\"token\":"+q(tok)+",\"expires\":"+expires);}


    static void validateLease(Properties p,String node,String tok,long now){if(node==null||tok==null)fail("lease token required");long epoch=Long.parseLong(p.getProperty("epoch"));long expires=Long.parseLong(p.getProperty("expires"));if(!p.getProperty("owner","").equals(node)||!tok.equals(token(node,epoch))||now>=expires)fail("stale or expired lease token");}
    static LinkedHashMap<String,String[]> hsm(Path d)throws Exception{LinkedHashMap<String,String[]>m=new LinkedHashMap<>();Path f=d.resolve("hsm.log");if(Files.exists(f))for(String l:Files.readAllLines(f)){if(l.isBlank())continue;String[]x=l.split("\\t",-1);if(x.length!=4)throw new IllegalArgumentException("bad hsm audit");m.put(x[0],x);}return m;}
    static String invokeHsm(Path d,String opid,String key,String digest)throws Exception{LinkedHashMap<String,String[]>m=hsm(d);if(m.containsKey(opid))return m.get(opid)[3];String sig=sha(key+"|"+digest+"|"+opid).substring(0,32);Files.writeString(d.resolve("hsm.log"),String.join("\t",opid,key,digest,sig)+"\n",StandardOpenOption.CREATE,StandardOpenOption.APPEND);return sig;}
    static String stableOp(String id,String digest)throws Exception{return "op-"+sha(id+"|"+digest).substring(0,20);}
    static boolean allowed(Properties p,String key,long now){if(Boolean.parseBoolean(p.getProperty("revoked."+key,"false")))return false;if(key.equals(p.getProperty("active_key")))return true;long grace=Long.parseLong(p.getProperty("grace."+key,"-1"));return now<=grace;}
    static String executionKey(Properties p,Req r){return r.key;}

    static void sign(Path d,Properties p,String[]a)throws Exception{
        String node=arg(a,"--node"),tok=arg(a,"--token"),rf=arg(a,"--request"),out=arg(a,"--out"),crash=arg(a,"--crash");long now=longArg(a,"--now");if(node==null||tok==null||rf==null||out==null)fail("sign arguments required");validateLease(p,node,tok,now);Map<String,String>in=requestFile(rf);String id=in.get("id"),digest=in.get("digest");LinkedHashMap<String,Req>m=requests(d);Req r=m.get(id);if(r!=null&& !r.digest.equals(digest))fail("request id conflict");

if(r!=null&&r.status.equals("COMMITTED")){json(Path.of(out),"\"id\":"+q(r.id)+",\"signature\":"+q(r.signature)+",\"key\":"+q(r.key)+",\"policy_generation\":"+r.policy);return;}if(r==null){r=new Req();r.id=id;r.digest=digest;r.key=p.getProperty("active_key");r.policy=Long.parseLong(p.getProperty("policy_gen"));r.status="PREPARED";r.signature=null;r.opid=stableOp(id,digest);}

        m.put(id,r);saveRequests(d,m);if("after_prepare".equals(crash))System.exit(75);
        String key=executionKey(p,r);LinkedHashMap<String,String[]>audit=hsm(d);String sig=audit.containsKey(r.opid)?audit.get(r.opid)[3]:null;if(sig==null){if(!allowed(p,key,now))fail("pinned key outside grace or revoked");sig=invokeHsm(d,r.opid,key,r.digest);}if("after_hsm".equals(crash))System.exit(75);r.signature=sig;r.status="COMMITTED";saveRequests(d,m);if("after_commit".equals(crash))System.exit(75);json(Path.of(out),"\"id\":"+q(r.id)+",\"signature\":"+q(sig)+",\"key\":"+q(key)+",\"policy_generation\":"+r.policy);
    }

    static void recover(Path d,Properties p,String[]a)throws Exception{String node=arg(a,"--node"),tok=arg(a,"--token"),out=arg(a,"--out");long now=longArg(a,"--now");if(node==null||tok==null||out==null)fail("recover arguments required");validateLease(p,node,tok,now);LinkedHashMap<String,Req>m=requests(d);int done=0;for(Req r:m.values())if(!r.status.equals("COMMITTED")){
String key=executionKey(p,r);LinkedHashMap<String,String[]>audit=hsm(d);String sig=audit.containsKey(r.opid)?audit.get(r.opid)[3]:null;if(sig==null){if(!allowed(p,key,now))fail("pinned key outside grace or revoked");sig=invokeHsm(d,r.opid,key,r.digest);}r.signature=sig;r.status="COMMITTED";
done++;}saveRequests(d,m);json(Path.of(out),"\"recovered\":"+done+",\"hsm_rows\":"+hsm(d).size());}

    static void rotate(Path d,Properties p,String[]a)throws Exception{String node=arg(a,"--node"),tok=arg(a,"--token"),key=arg(a,"--new-key");long now=longArg(a,"--now"),grace=longArg(a,"--grace-until");if(node==null||tok==null||key==null||key.isBlank())fail("rotate arguments required");validateLease(p,node,tok,now);if(grace<now)fail("grace deadline is before now");String old=p.getProperty("active_key");p.setProperty("grace."+old,Long.toString(grace));p.setProperty("active_key",key);p.setProperty("policy_gen",Long.toString(Long.parseLong(p.getProperty("policy_gen"))+1));p.setProperty("revoked."+key,"false");save(d,p);}
    static void revoke(Path d,Properties p,String[]a)throws Exception{String node=arg(a,"--node"),tok=arg(a,"--token"),key=arg(a,"--key");long now=longArg(a,"--now");if(node==null||tok==null||key==null)fail("revoke arguments required");validateLease(p,node,tok,now);p.setProperty("revoked."+key,"true");save(d,p);}
    static void status(Path d,Properties p,String[]a)throws Exception{Path out=Path.of(Objects.requireNonNull(arg(a,"--out"),"--out required"));json(out,"\"owner\":"+q(p.getProperty("owner","")) + ",\"epoch\":"+p.getProperty("epoch")+",\"expires\":"+p.getProperty("expires")+",\"active_key\":"+q(p.getProperty("active_key")) + ",\"policy_generation\":"+p.getProperty("policy_gen")+",\"request_count\":"+requests(d).size()+",\"hsm_rows\":"+hsm(d).size());}

    public static void main(String[]a)throws Exception{if(a.length==0)fail("command required");Path d=state(a);Files.createDirectories(d);if(a[0].equals("init")){long ms=longArg(a,"--lease-ms");String key=arg(a,"--key");if(key==null)fail("--key required");Properties p=new Properties();p.setProperty("owner","");p.setProperty("epoch","0");p.setProperty("expires","0");p.setProperty("lease_ms",Long.toString(ms));p.setProperty("active_key",key);p.setProperty("policy_gen","1");p.setProperty("revoked."+key,"false");save(d,p);Files.writeString(d.resolve("requests.tsv"),"");Files.writeString(d.resolve("hsm.log"),"");return;}try(Locked ignored=new Locked(d)){Properties p=load(d);switch(a[0]){case "acquire"->acquire(d,p,a);case "renew"->renew(d,p,a);case "check-lease"->{String node=arg(a,"--node"),tok=arg(a,"--token");validateLease(p,node,tok,longArg(a,"--now"));}case "sign"->sign(d,p,a);case "recover"->recover(d,p,a);case "rotate"->rotate(d,p,a);case "revoke"->revoke(d,p,a);case "status"->status(d,p,a);default->fail("unknown command");}}}
}

EOF_JAVA
rm -rf /tmp/signerctl-*
