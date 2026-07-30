# 赛智通前端

当前生产前端使用 React、TypeScript、Vite 和 Ant Design，包含首页、AI 推荐对话、竞赛库和“我的竞赛”页面。

## 本地运行

```powershell
npm install
npm run dev
```

创建 `frontend/.env.local`：

```env
VITE_API_BASE_URL=http://localhost:8000
```

后端在仓库根目录启动：

```powershell
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

## 构建

```powershell
npm run build
npm run preview
```

构建产物位于 `frontend/dist/`。

## 部署

`.github/workflows/deploy.yml` 会在 `main` 更新后自动构建并部署到 GitHub Pages。生产环境的 API 地址通过 `VITE_API_BASE_URL` 在构建时注入。

Supabase Secret/service-role key、DeepSeek Key 和 GitHub Token 都不能放入前端环境变量；这些密钥只应配置在 Render 或 GitHub Actions。
