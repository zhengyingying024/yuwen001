import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { fileURLToPath } from 'url';

// 获取 __dirname 等效值
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 确保目标目录存在
const templatesDir = path.resolve(__dirname, '../app/templates');
const assetsDir = path.resolve(templatesDir, 'assets');

if (!fs.existsSync(templatesDir)) {
  fs.mkdirSync(templatesDir, { recursive: true });
}

if (!fs.existsSync(assetsDir)) {
  fs.mkdirSync(assetsDir, { recursive: true });
}

// 构建 Vue 应用
console.log('正在构建 Vue 应用...');
execSync('npm run build', { stdio: 'inherit' });

// 检查生成的 CSS 文件名
const cssFiles = fs.readdirSync(assetsDir).filter(file => file.endsWith('.css'));
const cssFileName = cssFiles.length > 0 ? cssFiles[0] : 'index.css';

console.log(`检测到 CSS 文件: ${cssFileName}`);

// 创建一个简单的 index.html 文件，引用构建后的资源
const indexContent = `
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8">
    <link rel="icon" href="/assets/favicon.ico">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gemini API 代理服务</title>
    <script type="module" crossorigin src="/assets/main.js"></script>
    <link rel="stylesheet" href="/assets/${cssFileName}">
  </head>
  <body>
    <div id="app"></div>
  </body>
</html>
`;

// 将 index.html 写入到 app/templates 目录
const targetIndexPath = path.resolve(templatesDir, 'index.html');
fs.writeFileSync(targetIndexPath, indexContent);

console.log('构建完成！');
console.log(`- index.html 已创建到: ${targetIndexPath}`);
console.log(`- 静态资源已输出到: ${assetsDir}`);