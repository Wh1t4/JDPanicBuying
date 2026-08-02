import { useCallback, useEffect, useMemo, useState } from 'react'
import {
    AlertTriangle,
    BellRing,
    CheckCircle2,
    Clock3,
    ExternalLink,
    Loader2,
    LogIn,
    Monitor,
    PackageSearch,
    Play,
    RefreshCcw,
    ShieldCheck,
    ShoppingCart,
    Square,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'

type ApiResponse<T> = {
    data: T
    error?: string
    time?: string
}

type TaskStatus = {
    sku?: string
    title?: string
    area?: string
    status?: string
    message?: string
    last_check_time?: string
    last_stock_state?: string
    last_error?: string | null
    stock_provider?: 'page' | 'jos'
    manual_url?: string
    stop_requested?: boolean
    running?: boolean
    login?: boolean
    login_confirmed?: boolean
    cookies_saved?: boolean
    browser_report?: unknown
}

type AppConfig = {
    Spider?: {
        area?: string
        sku_id?: string
        amount?: number | string
        retry?: number | string
        timeout?: number | string
        work_count?: number | string
        submit_order?: boolean
        buy_time?: string
        stock_provider?: 'page' | 'jos'
    }
}

type FormState = {
    mode: '1' | '2'
    skurl: string
    area: string
    date: string
    count: string
    timeout: string
    retry: string
    work_count: string
    submit_order: boolean
    stock_provider: 'page' | 'jos'
}

type ManagedBrowserInfo = {
    login: boolean
    message?: string
    browser?: string
    cookie_count?: number
    current_url?: string
    title?: string
}

const defaultForm: FormState = {
    mode: '1',
    skurl: '',
    area: '',
    date: '',
    count: '1',
    timeout: '30',
    retry: '10',
    work_count: '1',
    submit_order: false,
    stock_provider: 'page',
}

async function api<T>(url: string, init?: RequestInit): Promise<T> {
    const response = await fetch(url, {
        headers: init?.body ? { 'content-type': 'application/json', ...(init.headers || {}) } : init?.headers,
        ...init,
    })
    const payload = (await response.json()) as ApiResponse<T>
    if (!response.ok || payload.error) {
        throw new Error(payload.error || `请求失败: ${response.status}`)
    }
    return payload.data
}

function toDatetimeLocal(value?: string) {
    if (!value) return ''
    return String(value).replace(' ', 'T').slice(0, 16)
}

function normalizeSku(value: string) {
    const trimmed = value.trim()
    const match = trimmed.match(/item\.jd\.com\/(\d{5,20})\.html/)
    if (match) return match[1]
    if (/^\d{5,20}$/.test(trimmed)) return trimmed
    return ''
}

function providerLabel(provider?: string) {
    return provider === 'jos' ? '开放平台' : '商品页'
}

function statusText(status: TaskStatus, isRunning: boolean, hasSavedLogin: boolean) {
    if (status.status === 'submitted') return { label: '已提交订单', variant: 'success' as const }
    if (status.status === 'success' && status.last_stock_state === 'checkout') return { label: '已到结算页', variant: 'success' as const }
    if (status.status === 'found') return { label: '发现可购', variant: 'success' as const }
    if (isRunning) return { label: '运行中', variant: 'default' as const }
    if (status.status === 'error' || status.last_error) return { label: '需处理', variant: 'warning' as const }
    if (hasSavedLogin) return { label: '已保存登录', variant: 'secondary' as const }
    return { label: '待配置', variant: 'outline' as const }
}

function StatBlock({ label, value }: { label: string; value?: string }) {
    return (
        <div className="min-h-20 rounded-md border bg-muted/35 p-3">
            <p className="mb-1 text-xs text-muted-foreground">{label}</p>
            <p className="break-words text-sm font-medium">{value || '-'}</p>
        </div>
    )
}

function App() {
    const [form, setForm] = useState<FormState>(() => {
        try {
            const saved = localStorage.getItem('jd_saved_form')
            if (saved) {
                const parsed = JSON.parse(saved)
                return {
                    ...defaultForm,
                    skurl: parsed.skurl ?? defaultForm.skurl,
                    area: parsed.area ?? defaultForm.area,
                    date: parsed.date ?? defaultForm.date,
                }
            }
        } catch (e) {
            // 忽略解析错误
        }
        return defaultForm
    })

    const [status, setStatus] = useState<TaskStatus>({})
    const [logText, setLogText] = useState('')
    const [busy, setBusy] = useState(false)
    const [qrOpen, setQrOpen] = useState(false)
    const [qrUrl, setQrUrl] = useState('')
    const [loginMessage, setLoginMessage] = useState('')
    const [dialog, setDialog] = useState('')
    const [managedBrowserInfo, setManagedBrowserInfo] = useState<ManagedBrowserInfo | null>(null)

    const sku = useMemo(() => normalizeSku(form.skurl), [form.skurl])
    const hasSavedLogin = Boolean(status.login || status.cookies_saved)
    const isConfirmedLogin = Boolean(status.login_confirmed)
    const isRunning = Boolean(status.running)
    const hasTask = Boolean(status.sku)
    const badge = useMemo(() => statusText(status, isRunning, hasSavedLogin), [hasSavedLogin, isRunning, status])

    useEffect(() => {
        localStorage.setItem('jd_saved_form', JSON.stringify({
            skurl: form.skurl,
            area: form.area,
            date: form.date,
        }))
    }, [form.skurl, form.area, form.date])

    function patchForm(patch: Partial<FormState>) {
        setForm((current) => ({ ...current, ...patch }))
    }

    const refreshStatus = useCallback(async () => {
        const data = await api<TaskStatus>('/api/task-status')
        setStatus(data || {})
    }, [])

    const refreshLog = useCallback(async () => {
        const data = await api<string>('/api/log')
        setLogText(data || '')
    }, [])

    const loadConfig = useCallback(async () => {
        const config = await api<AppConfig>('/api/config')
        const spider = config.Spider || {}

        let savedForm: Partial<FormState> = {}
        try {
            const saved = localStorage.getItem('jd_saved_form')
            if (saved) {
                savedForm = JSON.parse(saved)
            }
        } catch (e) { }

        setForm((current) => ({
            ...current,
            area: savedForm.area || spider.area || current.area,
            skurl: savedForm.skurl || (spider.sku_id ? `https://item.jd.com/${spider.sku_id}.html` : current.skurl),
            count: String(spider.amount || current.count),
            retry: String(spider.retry || current.retry),
            timeout: String(spider.timeout || current.timeout),
            work_count: String(spider.work_count || current.work_count),
            submit_order: Boolean(spider.submit_order ?? current.submit_order),
            date: savedForm.date || toDatetimeLocal(spider.buy_time) || current.date,
            stock_provider: spider.stock_provider === 'jos' ? 'jos' : 'page',
        }))
    }, [])

    async function runBusy(action: () => Promise<void>) {
        setBusy(true)
        try {
            await action()
        } catch (error) {
            setDialog(error instanceof Error ? error.message : '操作失败')
        } finally {
            setBusy(false)
        }
    }

    async function startLogin() {
        await runBusy(async () => {
            const data = await api<{ login: boolean; qrcode?: string; message?: string; cookies_saved?: boolean; login_confirmed?: boolean }>(
                '/api/login-qrcode',
                { method: 'POST', body: '{}' },
            )
            setLoginMessage(data.message || '')
            if (data.login) {
                setStatus((current) => ({
                    ...current,
                    login: true,
                    cookies_saved: Boolean(data.cookies_saved),
                    login_confirmed: Boolean(data.login_confirmed),
                }))
                setDialog(data.message || '登录状态已保存')
                return
            }
            setQrUrl(data.qrcode || '')
            setQrOpen(true)
        })
    }

    async function importBrowserLogin() {
        await runBusy(async () => {
            const data = await api<{ login: boolean; message?: string; cookies_saved?: boolean; login_confirmed?: boolean; browser?: string; cookie_count?: number }>(
                '/api/import-browser-login',
                { method: 'POST', body: '{}' },
            )
            setStatus((current) => ({
                ...current,
                login: Boolean(data.login),
                cookies_saved: Boolean(data.cookies_saved),
                login_confirmed: Boolean(data.login_confirmed),
            }))
            setDialog(data.message || '已导入浏览器登录态')
            await refreshStatus()
        })
    }

    async function openBrowserLogin() {
        await runBusy(async () => {
            const data = await api<{ ok: boolean; message?: string }>('/api/open-browser-login', { method: 'POST', body: '{}' })
            setDialog(data.message || '已打开专用京东浏览器')
        })
    }

    async function checkManagedBrowserStatus() {
        await runBusy(async () => {
            const data = await api<ManagedBrowserInfo>('/api/managed-browser-status', { method: 'POST', body: '{}' })
            setManagedBrowserInfo(data)
            setDialog(data.message || '已检查专用浏览器状态')
        })
    }

    const pollLogin = useCallback(async () => {
        const data = await api<{ login: boolean; message?: string; cookies_saved?: boolean; login_confirmed?: boolean }>('/api/login-poll')
        setLoginMessage(data.message || '等待扫码确认')
        if (data.login) {
            setStatus((current) => ({
                ...current,
                login: true,
                cookies_saved: Boolean(data.cookies_saved),
                login_confirmed: Boolean(data.login_confirmed),
            }))
            setQrOpen(false)
            setDialog(data.message || '扫码登录成功')
            await refreshStatus()
        }
    }, [refreshStatus])

    function validateForm() {
        if (!sku) throw new Error('请输入标准京东商品链接，或 5 到 20 位商品 ID')
        if (!form.area.trim()) throw new Error('地区 ID 不能为空')
        if (form.mode === '2' && !form.date) throw new Error('定时下单需要设置运行时间')
    }

    async function checkNow() {
        await runBusy(async () => {
            validateForm()
            const data = await api<{ message?: string; task?: TaskStatus }>('/api/check-stock', {
                method: 'POST',
                body: JSON.stringify({
                    skuid: sku,
                    area: form.area,
                    timeout: form.timeout,
                    stock_provider: form.stock_provider,
                }),
            })
            if (data.task) setStatus(data.task)
            setDialog(data.message || '检测完成')
            await refreshLog()
        })
    }

    async function startMonitor() {
        await runBusy(async () => {
            validateForm()
            const data = await api<{ message?: string; task?: TaskStatus }>('/api/jd-shopper', {
                method: 'POST',
                body: JSON.stringify({
                    mode: form.mode,
                    date: form.date,
                    area: form.area,
                    skuid: sku,
                    count: form.count,
                    retry: form.retry,
                    work_count: form.work_count,
                    submit_order: form.submit_order,
                    timeout: form.timeout,
                    stock_provider: form.stock_provider,
                }),
            })
            if (data.task) setStatus(data.task)
            setDialog(data.message || '监控已启动')
            await refreshLog()
        })
    }

    async function stopMonitor() {
        await runBusy(async () => {
            const data = await api<{ message?: string; task?: TaskStatus }>('/api/stop-task', { method: 'POST', body: '{}' })
            if (data.task) setStatus(data.task)
            setDialog(data.message || '已停止监控')
            await refreshLog()
        })
    }

    useEffect(() => {
        let cancelled = false
        async function boot() {
            try {
                await Promise.all([loadConfig(), refreshStatus(), refreshLog()])
            } catch (error) {
                if (!cancelled) setDialog(error instanceof Error ? error.message : '初始化失败')
            }
        }
        void boot()
        return () => {
            cancelled = true
        }
    }, [loadConfig, refreshLog, refreshStatus])

    useEffect(() => {
        if (!qrOpen) return
        const timer = window.setInterval(() => {
            pollLogin().catch((error) => setLoginMessage(error.message))
        }, 2000)
        return () => window.clearInterval(timer)
    }, [pollLogin, qrOpen])

    useEffect(() => {
        if (!isRunning) return
        const timer = window.setInterval(() => {
            refreshStatus().catch(() => undefined)
            refreshLog().catch(() => undefined)
        }, 3000)
        return () => window.clearInterval(timer)
    }, [isRunning, refreshLog, refreshStatus])

    return (
        <main className="min-h-screen bg-background text-foreground">
            <div className="border-b bg-card">
                <div className="mx-auto flex max-w-[1480px] flex-col gap-4 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
                    <div className="flex items-center gap-3">
                        <div className="grid h-11 w-11 place-items-center rounded-md bg-primary text-sm font-bold text-primary-foreground">
                            JD
                        </div>
                        <div>
                            <p className="text-xs font-medium uppercase text-muted-foreground">Local Client</p>
                            <h1 className="text-xl font-semibold tracking-normal">京东库存监控工作台</h1>
                        </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                        <Badge variant={badge.variant}>{badge.label}</Badge>
                        <Badge variant={isConfirmedLogin ? 'success' : hasSavedLogin ? 'warning' : 'outline'}>
                            {isConfirmedLogin ? '登录已验证' : hasSavedLogin ? '已保存 Cookies' : '未登录'}
                        </Badge>
                        <Badge variant="outline">{providerLabel(form.stock_provider)}</Badge>
                    </div>
                </div>
            </div>

            <div className="mx-auto grid max-w-[1480px] gap-5 px-5 py-5 xl:grid-cols-[310px_minmax(0,1fr)_390px]">
                <aside className="space-y-5">
                    <Card>
                        <CardHeader>
                            <CardTitle>账户链路</CardTitle>
                            <CardDescription>专用浏览器登录最稳，扫码登录作为备用。</CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-2">
                            <Button className="w-full justify-start" variant="outline" onClick={startLogin} disabled={busy}>
                                <LogIn className="h-4 w-4" />
                                {hasSavedLogin ? '重新扫码登录' : '扫码登录'}
                            </Button>
                            <Button className="w-full justify-start" variant="secondary" onClick={openBrowserLogin} disabled={busy}>
                                <Monitor className="h-4 w-4" />
                                打开专用京东浏览器
                            </Button>
                            <Button className="w-full justify-start" variant="secondary" onClick={checkManagedBrowserStatus} disabled={busy}>
                                <ShieldCheck className="h-4 w-4" />
                                检查专用浏览器
                            </Button>
                            <Button className="w-full justify-start" variant="secondary" onClick={importBrowserLogin} disabled={busy}>
                                <RefreshCcw className="h-4 w-4" />
                                导入浏览器登录态
                            </Button>

                            {managedBrowserInfo ? (
                                <div className="rounded-md border bg-muted/35 p-3 text-xs leading-6">
                                    <p>状态：{managedBrowserInfo.login ? '已登录' : '未登录'}</p>
                                    {managedBrowserInfo.cookie_count !== undefined ? <p>Cookies：{managedBrowserInfo.cookie_count}</p> : null}
                                    {managedBrowserInfo.title ? <p className="break-words">页面：{managedBrowserInfo.title}</p> : null}
                                </div>
                            ) : null}
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle>检测来源</CardTitle>
                            <CardDescription>开放平台需要先配置官方授权。</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <Tabs value={form.stock_provider} onValueChange={(value) => patchForm({ stock_provider: value === 'jos' ? 'jos' : 'page' })}>
                                <TabsList className="grid w-full grid-cols-2">
                                    <TabsTrigger value="page">商品页</TabsTrigger>
                                    <TabsTrigger value="jos">开放平台</TabsTrigger>
                                </TabsList>
                            </Tabs>
                        </CardContent>
                    </Card>
                </aside>

                <section className="space-y-5">
                    <Card>
                        <CardHeader>
                            <CardTitle>任务配置</CardTitle>
                            <CardDescription>填写商品、地区和运行参数后，可以先检测，再启动自动流程。</CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-5">
                            <div className="space-y-2">
                                <Label>运行模式</Label>
                                <Tabs value={form.mode} onValueChange={(value) => patchForm({ mode: value === '2' ? '2' : '1' })}>
                                    <TabsList className="grid w-full grid-cols-2">
                                        <TabsTrigger value="1">有货自动下单</TabsTrigger>
                                        <TabsTrigger value="2">定时下单</TabsTrigger>
                                    </TabsList>
                                </Tabs>
                            </div>

                            <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(220px,0.6fr)]">
                                <div className="space-y-2">
                                    <Label htmlFor="goods-link">商品链接或 SKU</Label>
                                    <Input
                                        id="goods-link"
                                        value={form.skurl}
                                        onChange={(event) => patchForm({ skurl: event.target.value })}
                                        placeholder="https://item.jd.com/100021044189.html"
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="area">地区 ID</Label>
                                    <Input id="area" value={form.area} onChange={(event) => patchForm({ area: event.target.value })} placeholder="1_72_2799_0" />
                                </div>
                            </div>

                            <div className="grid gap-4 md:grid-cols-5">
                                <div className="space-y-2 md:col-span-2">
                                    <Label htmlFor="run-at">运行时间</Label>
                                    <Input id="run-at" type="datetime-local" value={form.date} onChange={(event) => patchForm({ date: event.target.value })} disabled={form.mode === '1'} />
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="count">数量</Label>
                                    <Input id="count" type="number" min="1" max="999" value={form.count} onChange={(event) => patchForm({ count: event.target.value })} />
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="timeout">间隔秒</Label>
                                    <Input id="timeout" type="number" min="1" max="1000" value={form.timeout} onChange={(event) => patchForm({ timeout: event.target.value })} />
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="retry">重试</Label>
                                    <Input id="retry" type="number" min="1" max="1000" value={form.retry} onChange={(event) => patchForm({ retry: event.target.value })} />
                                </div>
                            </div>

                            <div className="flex flex-col gap-4 rounded-md border border-amber-200 bg-amber-50 p-4 text-amber-950 md:flex-row md:items-center md:justify-between">
                                <div className="flex min-w-0 items-start gap-3">
                                    <ShoppingCart className="mt-0.5 h-5 w-5 shrink-0" />
                                    <div>
                                        <p className="font-medium">自动点击提交订单</p>
                                        <p className="text-sm text-amber-800">关闭时只进入结算页并定位按钮；开启后会真实点击提交。</p>
                                    </div>
                                </div>
                                <Button type="button" variant={form.submit_order ? 'destructive' : 'outline'} onClick={() => patchForm({ submit_order: !form.submit_order })}>
                                    {form.submit_order ? '已开启' : '保持关闭'}
                                </Button>
                            </div>

                            <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
                                <Button variant="outline" onClick={() => setForm(defaultForm)} disabled={busy}>
                                    重置
                                </Button>
                                <Button variant="secondary" onClick={checkNow} disabled={busy}>
                                    {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <PackageSearch className="h-4 w-4" />}
                                    立即检测
                                </Button>
                                <Button onClick={startMonitor} disabled={busy || isRunning}>
                                    {form.mode === '2' ? <Clock3 className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                                    {isRunning ? '运行中' : form.mode === '2' ? '启动定时下单' : '开始自动下单'}
                                </Button>
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                            <div>
                                <CardTitle>日志</CardTitle>
                                <CardDescription>服务端实时输出。</CardDescription>
                            </div>
                            <Button variant="ghost" onClick={() => runBusy(refreshLog)} disabled={busy}>
                                <RefreshCcw className="h-4 w-4" />
                                刷新
                            </Button>
                        </CardHeader>
                        <CardContent>
                            <Textarea value={logText} readOnly className="min-h-80 resize-y bg-zinc-950 font-mono text-xs leading-relaxed text-zinc-50" />
                        </CardContent>
                    </Card>
                </section>

                <aside className="space-y-5">
                    <Card>
                        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                            <div>
                                <CardTitle>运行状态</CardTitle>
                                <CardDescription>当前任务、库存和错误诊断。</CardDescription>
                            </div>
                            <Button variant="ghost" size="icon" onClick={() => runBusy(refreshStatus)} disabled={busy}>
                                <RefreshCcw className="h-4 w-4" />
                                <span className="sr-only">刷新状态</span>
                            </Button>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="grid grid-cols-2 gap-3">
                                <StatBlock label="SKU" value={status.sku} />
                                <StatBlock label="状态" value={status.status || (isRunning ? 'running' : '-')} />
                                <StatBlock label="库存" value={status.last_stock_state || '未检测'} />
                                <StatBlock label="检查时间" value={status.last_check_time} />
                            </div>

                            {hasTask ? (
                                <div className="rounded-md border bg-background p-3">
                                    <div className="flex items-start gap-2">
                                        {status.status === 'found' ? (
                                            <BellRing className="mt-0.5 h-4 w-4 text-emerald-600" />
                                        ) : status.last_error ? (
                                            <AlertTriangle className="mt-0.5 h-4 w-4 text-amber-600" />
                                        ) : (
                                            <CheckCircle2 className="mt-0.5 h-4 w-4 text-muted-foreground" />
                                        )}
                                        <div className="min-w-0">
                                            <p className="text-sm font-medium">{status.message || '暂无说明'}</p>
                                            {status.last_error ? <p className="mt-1 text-sm text-muted-foreground">{status.last_error}</p> : null}
                                            {status.manual_url ? (
                                                <a className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-primary underline-offset-4 hover:underline" href={status.manual_url} target="_blank" rel="noreferrer">
                                                    打开京东商品页
                                                    <ExternalLink className="h-3.5 w-3.5" />
                                                </a>
                                            ) : null}
                                        </div>
                                    </div>
                                </div>
                            ) : (
                                <div className="grid min-h-36 place-items-center rounded-md border border-dashed px-5 text-center text-sm text-muted-foreground">
                                    配置商品后可以立即检测，或直接启动自动流程。
                                </div>
                            )}

                            <div className="grid gap-3">
                                <Button variant="secondary" onClick={checkNow} disabled={busy}>
                                    <PackageSearch className="h-4 w-4" />
                                    立即检测
                                </Button>
                                <Button variant="destructive" onClick={stopMonitor} disabled={busy || !isRunning}>
                                    <Square className="h-4 w-4" />
                                    停止监控
                                </Button>
                            </div>
                        </CardContent>
                    </Card>
                </aside>
            </div>

            <Dialog open={qrOpen} onOpenChange={setQrOpen}>
                <DialogContent className="sm:max-w-sm">
                    <DialogHeader>
                        <DialogTitle>京东扫码登录</DialogTitle>
                        <DialogDescription>使用京东 App 扫码并确认登录。</DialogDescription>
                    </DialogHeader>
                    {qrUrl ? <img src={qrUrl} alt="京东登录二维码" className="mx-auto h-56 w-56 rounded-md border object-contain" /> : null}
                    <p className="text-center text-sm text-muted-foreground">{loginMessage || '等待扫码确认'}</p>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setQrOpen(false)}>
                            关闭
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            <Dialog open={Boolean(dialog)} onOpenChange={(open) => !open && setDialog('')}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>提示</DialogTitle>
                        <DialogDescription>{dialog}</DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button onClick={() => setDialog('')}>确定</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </main>
    )
}

export default App