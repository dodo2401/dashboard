# AI 动画流水线面板

这是一个纯静态单页应用，外部用户只需要打开 `index.html` 对应的网页地址，即可远程加载或上传 `node_outputs.json`。

## 使用方式

1. 打开部署后的页面地址。
2. 粘贴远程 JSON URL，点击“加载”。
3. 或点击“上传 JSON”，选择本地 `.json` / `.gz` 文件。
4. 加载远程 URL 后，可点击“复制分享链接”，把带 `?src=` 参数的页面链接发给其他人。

## 部署方式

把整个 `pipeline_dashboard` 目录上传到任意静态托管服务即可，例如：

- 内网静态服务
- Nginx / Apache
- GitHub Pages
- Vercel / Netlify
- OSS / CDN 静态站点

本地预览：

```bash
cd pipeline_dashboard
python3 -m http.server 8123
```

然后打开：

```text
http://127.0.0.1:8123/index.html
```

## 注意

如果远程 JSON 所在服务器不允许浏览器跨域读取，页面会提示加载失败。此时请先下载 JSON 文件，再使用“上传 JSON”导入。
