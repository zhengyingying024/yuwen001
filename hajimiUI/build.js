import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { fileURLToPath } from 'url';

// 获取 __dirname 等效值
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 构建 Vue 应用
console.log('正在构建 Vue 应用...');
execSync('npm run build', { stdio: 'inherit' });

// 确保目标目录存在
const assetsDir = path.resolve(__dirname, '../app/templates/assets');
if (!fs.existsSync(assetsDir)) {
  fs.mkdirSync(assetsDir, { recursive: true });
}

// 读取构建后的 index.html
const distIndexPath = path.resolve(__dirname, 'dist/index.html');
let indexContent = fs.readFileSync(distIndexPath, 'utf8');

// 修改 index.html 中的资源路径
indexContent = indexContent.replace(/\/assets\//g, '/assets/');

// 将修改后的 index.html 写入到 app/templates 目录
const targetIndexPath = path.resolve(__dirname, '../app/templates/index.html');
fs.writeFileSync(targetIndexPath, indexContent);

console.log('构建完成！');
console.log(`- index.html 已复制到: ${targetIndexPath}`);
console.log(`- 静态资源已复制到: ${assetsDir}`);