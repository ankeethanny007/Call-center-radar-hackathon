const API=process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export default async function Home(){
 const calls=await fetch(`${API}/attention`,{cache:"no-store"}).then(r=>r.json()).catch(()=>[]);
 return <><h1>Manager attention queue</h1><p>Calls are ranked only after persistent, evidence-backed analysis completes.</p><section>{calls.length ? calls.map((c:any)=><a className="card" href={`/calls/${c.id}`} key={c.id}><strong>{c.id}</strong><span>Attention score: {c.attention_score}/100</span><small>{c.customer_id || "No customer ID"} · {c.status}</small></a>) : <div className="empty">No processed calls yet. Ingest a dataset manifest, then run the processor.</div>}</section></>
}
