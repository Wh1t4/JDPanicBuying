new Vue({
    el: "#app",
    data() {
      return {
        mode: "1", // 模式：定时监控/有货提醒
        date: "",
        area: "", // 所在地区
        skurl: "", // 商品url
        count: "1", // 监控数量
        retry: "10", // 重试次数
        work_count: "1", // 启动线程数
        timeout: "30", // 超时时间
        stock_provider: "page",
        eid: "",
        fp: "",
        timeSelectAble: true,
        dialogVisible: false,
        dialog: "",
        skuid: "",
        title: "错误",
        qrVisible: false,
        qrUrl: "",
        loginMessage: "",
        loginTimer: undefined,
        task: true,
        logTimer: undefined,
        statusTimer: undefined,
        statusText: "",
        taskStatus: {},
        logText: "",
        isBusy: false
      };
    },
    computed: {
      hasStatus() {
        return Boolean(this.taskStatus && this.taskStatus.sku)
      },
      isLoggedIn() {
        return Boolean(this.taskStatus && this.taskStatus.login)
      },
      isLoginConfirmed() {
        return Boolean(this.taskStatus && this.taskStatus.login_confirmed)
      },
      hasSavedCookies() {
        return Boolean(this.taskStatus && this.taskStatus.cookies_saved)
      },
      accountBadgeText() {
        if (this.isLoginConfirmed) return "已登录"
        if (this.hasSavedCookies || this.isLoggedIn) return "已保存"
        return "未登录"
      },
      isRunning() {
        return Boolean(this.taskStatus && this.taskStatus.running)
      },
      statusBadgeText() {
        if (!this.hasStatus) return "待配置"
        if (this.taskStatus.status === "found") return "发现可能有货"
        if (this.taskStatus.running) return "监控中"
        if (this.taskStatus.status === "error" || this.taskStatus.last_error) return "需要处理"
        if (this.taskStatus.login) return "已保存"
        return "就绪"
      },
      statusBadgeClass() {
        return {
          success: this.statusBadgeText === "发现可能有货" || this.statusBadgeText === "已登录",
          warning: this.statusBadgeText === "需要处理",
          active: this.statusBadgeText === "监控中"
        }
      }
    },
    mounted() {
      setTimeout(() => {
        this.main()
      }, 100)
    },
    methods: {
      main() {
        this.loadConfig()
        this.refreshStatus()
      },
      loadConfig() {
        fetch('./api/config')
        .then(response => response.json())
        .then(res => {
          if (!res.data || !res.data.Spider) return
          const spider = res.data.Spider
          this.area = spider.area || this.area
          this.skurl = spider.sku_id ? `https://item.jd.com/${spider.sku_id}.html` : this.skurl
          this.count = spider.amount || this.count
          this.retry = spider.retry || this.retry
          this.timeout = spider.timeout || this.timeout
          this.stock_provider = this.normalizeStockProvider(spider.stock_provider || this.stock_provider)
          this.eid = spider.eid || this.eid
          this.fp = spider.fp || this.fp
          if (spider.buy_time) {
            this.date = this.toDatetimeLocal(spider.buy_time)
          }
        })
      },
      toDatetimeLocal(value) {
        if (!value) return ""
        return String(value).replace(" ", "T").slice(0, 16)
      },
      refreshStatus() {
        this.isBusy = true
        fetch('./api/task-status')
        .then(response => response.json())
        .then(res => {
          const data = res.data || {}
          this.updateStatusText(data)
          if (data.running) {
            this.task = false
            this.getLog()
            this.ensureStatusTimer()
          }
        })
        .catch(error => {
          this.dialogShow(error.message || "状态刷新失败")
        })
        .finally(() => {
          this.isBusy = false
        })
      },
      setMode(value) {
        this.mode = value
        this.buyMode(value)
      },
      normalizeStockProvider(value) {
        return value === "jos" ? "jos" : "page"
      },
      startLogin() {
        this.isBusy = true
        fetch('./api/login-qrcode', { method: 'POST' })
        .then(response => response.json())
        .then(res => {
          this.loginMessage = res.data.message || ""
          if (res.data.login) {
            this.taskStatus = Object.assign({}, this.taskStatus, {
              login: true,
              login_confirmed: Boolean(res.data.login_confirmed),
              cookies_saved: Boolean(res.data.cookies_saved)
            })
            this.dialogShow(this.loginMessage)
            this.refreshStatus()
            return
          }
          this.qrUrl = res.data.qrcode || ""
          this.qrVisible = true
          this.startLoginPoll()
        })
        .catch(error => {
          this.dialogShow(error.message || "二维码生成失败")
        })
        .finally(() => {
          this.isBusy = false
        })
      },
      startLoginPoll() {
        if (this.loginTimer) {
          clearInterval(this.loginTimer)
        }
        this.loginTimer = setInterval(() => {
          fetch('./api/login-poll')
          .then(response => response.json())
          .then(res => {
            this.loginMessage = res.data.message || "等待扫码确认"
            if (res.data.login) {
              this.taskStatus = Object.assign({}, this.taskStatus, {
                login: true,
                login_confirmed: Boolean(res.data.login_confirmed),
                cookies_saved: Boolean(res.data.cookies_saved)
              })
              this.stopLoginPoll()
              this.dialogShow(this.loginMessage)
              this.refreshStatus()
            }
          })
        }, 2000)
      },
      stopLoginPoll() {
        this.qrVisible = false
        if (this.loginTimer) {
          clearInterval(this.loginTimer)
          this.loginTimer = undefined
        }
      },
      updateStatusText(data) {
        if (!data || !data.sku) {
          this.statusText = ""
          this.taskStatus = data || {}
          return
        }
        this.taskStatus = data
        let lines = [`SKU: ${data.sku}`]
        if (data.status) lines.push(`状态: ${data.status}`)
        if (data.message) lines.push(`说明: ${data.message}`)
        if (data.login !== undefined) lines.push(`登录: ${data.login ? "已登录" : "未登录"}`)
        if (data.cookies_saved !== undefined) lines.push(`Cookies: ${data.cookies_saved ? "已保存" : "未保存"}`)
        if (data.last_stock_state) lines.push(`库存: ${data.last_stock_state}`)
        if (data.last_check_time) lines.push(`检查: ${data.last_check_time}`)
        if (data.last_error) lines.push(`错误: ${data.last_error}`)
        this.statusText = lines.join("\n")
      },
      ensureStatusTimer() {
        if (this.statusTimer) return
        this.statusTimer = setInterval(() => {
          fetch('./api/task-status')
          .then(response => response.json())
          .then(res => {
            this.updateStatusText(res.data)
            if (!res.data || !res.data.running) {
              clearInterval(this.statusTimer)
              this.statusTimer = undefined
            }
          })
        }, 3000)
      },
      upload() {
        if (!this.checkValid()) return
        this.isBusy = true
        let url = "./api/jd-shopper"
        let data = {
          mode: this.mode,
          date: this.date,
          area: this.area,
          skuid: this.skuid,
          count: this.count,
          retry: this.retry,
          work_count: this.work_count,
          timeout: this.timeout,
          stock_provider: this.normalizeStockProvider(this.stock_provider),
          eid: this.eid,
          fp: this.fp,
        };
        fetch(url, {
          body: JSON.stringify(data), // must match 'Content-Type' header
          cache: 'no-cache', // *default, no-cache, reload, force-cache, only-if-cached
          credentials: 'same-origin', // include, same-origin, *omit
          headers: {
            'content-type': 'application/json'
          },
          method: 'POST', // *GET, POST, PUT, DELETE, etc.
          mode: 'same-origin', // no-cors, cors, *same-origin
          redirect: 'follow', // manual, *follow, error
          referrer: 'no-referrer', // *client, no-referrer
        }).then(response => {
          if (!response.ok) {
            throw new Error(`请求失败: ${response.status}`)
          }
          return response.json()
        }).then(res => {
          console.log(res)
          this.dialogShow(res.data.message || "监控任务已启动")
          if (res.data.started || res.data.running) {
            this.updateStatusText(res.data.task)
            this.getLog()
            this.task = false
            this.ensureStatusTimer()
          }
        }).catch(error => {
          this.dialogShow(error.message || "启动任务失败")
        }).finally(() => {
          this.isBusy = false
        })
      },
      buyMode(value) {
        if (this.mode === "1" || this.mode === 1) {
          this.timeSelectAble = true;
        } else {
          this.timeSelectAble = false;
        }
      },
      reset() {
        this.mode = "1" // 模式：定时监控/有货提醒
        this.date = ""
        this.area = "" // 所在地区
        this.skurl = "" // 商品url
        this.count = "1" // 监控数量
        this.retry = "10" // 重试次数
        this.work_count = "1" // 启动线程数
        this.timeout = "3" // 超时时间
        this.stock_provider = "page"
        this.eid = ""
        this.fp = ""
      },
      dialogShow(mes) {
        this.dialog = mes
        this.dialogVisible = true
      },
      showForm() {
        this.task = true
        if (this.logTimer) {
          clearInterval(this.logTimer)
          this.logTimer = undefined
        }
        if (this.statusTimer) {
          clearInterval(this.statusTimer)
          this.statusTimer = undefined
        }
      },
      stopTask() {
        this.isBusy = true
        fetch('./api/stop-task', { method: 'POST' })
        .then(response => response.json())
        .then(res => {
          this.dialogShow(res.data.message || "已请求停止监控任务")
          this.updateStatusText(res.data.task)
          this.getLog()
        })
        .catch(error => {
          this.dialogShow(error.message || "停止任务失败")
        })
        .finally(() => {
          this.isBusy = false
        })
      },
      checkNow() {
        if (!this.checkValid()) return
        this.isBusy = true
        const data = {
          skuid: this.skuid,
          area: this.area,
          timeout: this.timeout,
          stock_provider: this.normalizeStockProvider(this.stock_provider)
        }
        fetch('./api/check-stock', {
          body: JSON.stringify(data),
          headers: { 'content-type': 'application/json' },
          method: 'POST',
          mode: 'same-origin'
        })
        .then(response => response.json())
        .then(res => {
          this.dialogShow(res.data.message || "检测完成")
          this.updateStatusText(res.data.task)
          this.getLog()
        })
        .catch(error => {
          this.dialogShow(error.message || "检测失败")
        })
        .finally(() => {
          this.isBusy = false
        })
      },
      checkValid() {
        if (this.area == "" || this.skurl == "") {
          this.dialogShow("地区ID与商品链接不能为空")
          return false
        }
        else if (this.mode == "2" && this.date == "") {
          this.dialogShow("定时监控需设置时间")
          return false
        }
        let skuid = this.skurl.match(/item\.jd\.com\/(\d{5,20})\.html/)
        skuid = skuid ? skuid[1] : null
        if (skuid == null) {
          skuid = this.skurl.trim()
          let reNum = /^\d{5,20}$/
          if (!reNum.test(skuid)) {
            this.dialogShow("请输入标准京东商品链接，或5到20位商品ID")
            return false
          }
        }
        this.skuid = skuid
        return true
      },
      getLog() {
        let url = './api/log'

        fetch(url)
        .then(response => {
          return response.json();
        })
        .then(res => {
          console.log(res.data);
          this.logText = res.data || ""
        });

        if (this.logTimer) {
          clearInterval(this.logTimer)
        }
        this.logTimer = setInterval(() => {
          fetch(url)
          .then(response => {
            return response.json();
          })
          .then(res => {
            console.log(res.data);
            this.logText = res.data || ""
          });
        }, 10000)
      }
    },
  });


// confirm,e.prototype.$prompt=ya.prompt,e.prototype.$notify=tl,e.prototype.$message=ou};
//"undefined"!=typeof window&&window.Vue&&Ld(window.Vue);t.default={version:"2.15.0",
//locale:j.use,i18n:j.i18n,install:Ld,CollapseTransition:ii,Loading:_l,Pagination:pt,
//Dialog:gt,Autocomplete:kt,Dropdown:At,DropdownMenu:Bt,DropdownItem:Wt,Menu:ei,
//Submenu:ai,MenuItem:di,MenuItemGroup:vi,Input:ne,InputNumber:_i,Radio:Si,RadioGroup:Mi,
//RadioButton:Ii,Checkbox:Vi,CheckboxButton:Ri,CheckboxGroup:Yi,Switch:Xi,Select:ct,
//Option:ht,OptionGroup:en,Button:Et,ButtonGroup:Pt,Table:Un,TableColumn:ir
