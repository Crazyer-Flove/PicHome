# Luma · 流光

一个简约的 Windows 10/11 x64 GitHub 图床客户端。拖拽、选择文件或 Ctrl+V 粘贴截图，上传后复制图片直链或 Markdown。

默认图片仓库：https://github.com/Crazyer-Flove/PicHome ，分支 `main`，目录 `images/YYYY/MM/随机文件名`。

## 第一次使用

1. 双击 `Luma.exe`，点击右上角「连接设置」。无需安装 Python。
2. 点击「前往 GitHub 创建 Token」，创建 Fine-grained personal access token。
3. Resource owner 选择自己的账号；Repository access 仅选择 `PicHome`；Repository permissions 中将 **Contents** 设置为 **Read and write**。设置合适的到期时间，到期后在软件中更新 Token。
4. 将 Token 粘贴到软件中，点击「测试连接」，然后「保存设置」。测试连接检查公开仓库和分支可访问性，第一次实际上传验证写入权限。不要将 Token 发给他人或提交到仓库。
5. 拖入图片、点击选择图片，或复制截图后在主窗口按 Ctrl+V。多张文件按队列串行上传。
6. 上传记录分别提供「复制直链」「复制 Markdown」「打开图片」。历史记录保留最近 500 条。

## 链接与保存

链接形如 `https://raw.githubusercontent.com/Crazyer-Flove/PicHome/<commit-sha>/images/2026/10/<id>.png`，固定到上传提交，不含 Token，也不使用临时下载链接。原始图片格式保持不变，截图保存为 PNG。支持 PNG/JPEG/GIF/WebP/BMP/TIFF/AVIF，单张上限为本工具设定的 20 MiB。部分浏览器可能下载而非预览 TIFF 等格式，推荐 PNG/JPEG/WebP。

链接长期可用依赖于 GitHub 服务、公开仓库和对应提交仍存在。仓库删除、变为私有、历史重写等操作可能使链接失效。GitHub 在部分网络中访问可能较慢，本工具不承诺绝对永久可用。所有上传图片公开可访问。

设置与历史存放在 `%LOCALAPPDATA%\Luma`。Token 使用 Windows DPAPI 绑定当前 Windows 用户加密；exe 和源代码不包含凭据。换电脑或换 Windows 用户后需重新填写 Token。上传失败会显示错误，可重新选择原图片重试；工具不会自动删除远程图片。

## 本地构建

Windows x64 + Python 3.10 或更高版本，运行 `powershell -ExecutionPolicy Bypass -File build.ps1`。产物在 `dist/Luma.exe`。单文件启动时会解压依赖，首次启动可能需要数秒。软件未做商业代码签名，Windows 可能显示发布者未验证。

核心接口依据 [GitHub Contents API](https://docs.github.com/en/rest/repos/contents#create-or-update-file-contents)；仓库容量参考 [GitHub 文件与仓库限制](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)。建议用于个人、小规模图片分享，定期备份重要图片。

## 验证

`python -m unittest -v test_core` 检查上传负载、固定提交链接、随机文件名、Windows 凭据加密、文件限制和错误处理。公开仓库示例图片用于验证 GitHub 直链；客户端上传需要配置个人 Token。

修复版本补齐构建环境 SSL 模块所依赖的证书数据文件，解决独立 exe 在初始化 HTTPS 时报告文件缺失的问题；保持 HTTPS 证书验证。`Luma.exe --network-test` 可进行不读取 Token 的公开连通性检查，结果写入当前目录 `network-check.json`。
