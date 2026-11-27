# Seenical GitBook

Seenical GitBook 是知见 Seenical 的网站模板，用于发布产品文档、使用指南和常见问答。

## 快速开始

登录 [知见 Seenical](https://seenical.ai)，选择产品，在「站点」中创建托管网站。将写作计划关联到站点，生成并发布文章。

## 本地构建

使用 Node.js 10.24.1、GitBook CLI 2.3.2 和 Python 3，运行 `make build`。构建结果在 `.build/_book`，运行 `make package` 可生成 `book.tar.gz`。

源码按语言存放，每个语言目录都有自己的样式、Logo 和图标。默认语言的首页、文章和资源发布到站点根路径，其他语言使用各自的目录。修改默认语言后，发布时会切换公开路径，已发布文章的网址可能变化。
