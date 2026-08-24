import "./styles.css";
export default function Layout({children}:{children:React.ReactNode}) { return <html><body><header><a href="/">Call-Centre Radar</a><nav><a href="/">Attention queue</a><a href="/customers">Customers</a></nav></header><main>{children}</main></body></html> }
