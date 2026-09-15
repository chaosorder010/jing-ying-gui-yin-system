import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, setToken } from '../api'

export function CallbackPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [error, setError] = useState('')

  useEffect(() => {
    const code = params.get('code')
    if (!code) {
      setError('缺少授权 code')
      return
    }
    let cancelled = false
    api
      .callback(code)
      .then((res) => {
        if (cancelled) return
        setToken(res.access_token)
        navigate('/workbench', { replace: true })
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message || '登录失败')
      })
    return () => {
      cancelled = true
    }
  }, [params, navigate])

  return (
    <div className="login-page">
      <div className="login-panel">
        <p className="brand">经营归因</p>
        <h1>{error ? '登录失败' : '正在完成授权…'}</h1>
        {error && <p className="error">{error}</p>}
      </div>
    </div>
  )
}
