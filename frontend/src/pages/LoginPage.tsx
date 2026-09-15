export function LoginPage() {
  return (
    <div className="login-page">
      <div className="login-panel">
        <p className="brand">经营归因</p>
        <h1>分析工作台</h1>
        <p className="sub">围绕业务问题持续追问、补充证据、沉淀阶段性结论</p>
        <div className="login-actions">
          {/* 走同源 /auth 代理，避免浏览器跨端口拦截 */}
          <a className="btn primary" href="/auth/login">
            授权登录
          </a>
          <a className="btn ghost" href="/auth/login?role=admin">
            管理员登录
          </a>
        </div>
      </div>
    </div>
  )
}
