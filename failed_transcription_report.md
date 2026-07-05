# vtext-server 转录失败问题报告

## 概述
批量处理 450 个视频（投资训练营课程），70 个转录失败（15.6%），服务器报错：
```
Failed to process uploaded file: could not determine content size in frame header
```

## 环境
- **服务器**：192.168.0.122:8000 (v0.1.5, small model, 2 workers)
- **客户端**：vtext_client (Windows, ffmpeg D:\ffmpeg\bin\ffmpeg.exe)
- **输入**：F:\downloads\allwin\投资训练营 (450 mp4)
- **时间**：2026-06-27（任务运行约 12 小时）

## 失败特征

### 按文件夹统计（失败数 / 总数）
```
老莫教研团队：基础篇        16/16  ← 全灭
周昭特训营：进阶篇          18/36
昊楠主力军团：高级篇         6/8
周昭特训营：高级篇           5/27
韩珂龙头班：进阶篇           4/24
周昭特训营：基础篇           4/14
李彦鹏量化班：基础篇         3/6
... (共 15 个受影响的文件夹)
```

### 文件大小特征
- **失败视频**：min=93MB, max=850MB, avg=286MB
- **成功视频**：avg=128MB
- 明显规律：**大文件失败率高**

### 编码信息（抽样验证）
```bash
ffprobe 七、中军趋势龙.mp4
# codec_name=h264, width=1920, height=1080
# 文件本身无损坏，ffprobe 能正常解析
```

## 已确认非问题
- ❌ 文件损坏（本地 ffprobe 正常）
- ❌ 客户端 ffmpeg 问题（成功的 380 个用同一 ffmpeg）
- ❌ 网络问题（上传成功，服务器才报错）

## 推测原因
1. 服务器端 whisper.cpp/ffmpeg 对大文件或特定 h264 profile 的兼容性问题
2. 服务器端某个缓冲区/超时限制未适配大文件
3. 这批课程录制时用的编码参数触发了服务器端的边界条件

## 重现步骤
1. 任选失败列表中的一个视频（如 `李彦鹏量化班：基础篇/第五节：波段核心模型.mp4`, 850MB）
2. 用 vtext-client 提交转录
3. 观察服务器日志中的错误

## 建议排查方向
1. 升级服务器端 whisper.cpp 到最新版本
2. 检查服务器端 ffmpeg 日志，看具体在哪一步失败
3. 尝试手动在服务器上用 ffmpeg 提取其中一个失败视频的 WAV：
   ```bash
   ffmpeg -i 失败视频.mp4 -ar 16000 -ac 1 -f wav test.wav
   ```
4. 如果 ffmpeg 能成功提取 WAV，问题在 whisper.cpp；否则在 ffmpeg 参数

## 附：失败文件清单
见附件 `failed_70_videos.txt`（完整路径列表，方便服务器端批量测试）

---
报告人：Client (ronliu014)
日期：2026-06-27
