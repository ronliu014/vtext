# vtext 模型选择指南

---

## 可用模型

| 模型 | 大小 | 英文效果 | 中文效果 | 推荐场景 |
|------|------|----------|----------|----------|
| `tiny` | 75 MB | 一般 | ❌ 无法识别 | 快速原型、英文测试 |
| `base` | 142 MB | 良好 | ❌ 错误率高 | 英文单语言场景 |
| `small` | 466 MB | 很好 | ✅ 准确 | **中文推荐最低配置** |
| `medium` | 1.5 GB | 优秀 | ✅ 很准确 | 高精度多语言 |
| `large-v3` | 3.1 GB | 最佳 | ✅ 最准确 | 生产环境、专业用途 |

---

## 实测结论（基于真实音频测试）

### 中文识别

测试音频：21 秒中文语音，内容为「人工智能技术正在改变我们的生活方式……」

| 模型 | 不指定语言 | 指定 `-l zh` | 结论 |
|------|-----------|-------------|------|
| `base` | 输出英文乱译 | 有明显错字（"与音试别"、"維文字"） | ❌ 不可用 |
| `small` | ✅ 自动检测为中文，完全正确 | ✅ 完全正确，时间戳切分准确 | ✅ 推荐 |

**base 不指定语言时会把中文误识别为英文**，即使指定 `-l zh` 也有较多错字。
**中文场景必须使用 small 及以上模型**。

### 英文识别

测试音频：JFK 演讲片段（「Ask not what your country can do for you...」）

| 模型 | 输出 |
|------|------|
| `tiny` | `And so, my fellow Americans, ask not what your country can do for you...` |
| `base` | `And so my fellow Americans ask not what your country can do for you...` |
| `small` | 与 base 一致，标点略有差异 |

英文场景下 tiny/base 已足够准确，small 提升有限。

---

## 下载模型

```sh
# 通过 vtext-server 内置命令下载
vtext-server model download tiny
vtext-server model download base
vtext-server model download small

# 或手动从 HuggingFace 下载到 models_dir
curl -L -o ~/.cache/vtext/models/ggml-small.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin
```

默认 `models_dir` 为 `~/.cache/vtext/models/`，可通过配置文件修改：

```toml
# ~/.config/vtext/server.toml
models_dir = "/data/models/vtext"
```

---

## 选型建议

- **纯英文内容**：`base` 即可，速度快、占用低
- **中文或多语言内容**：`small` 起步，对精度要求高用 `medium`
- **生产环境**：`large-v3`，精度最高，需要较多内存和算力
- **资源受限（树莓派等）**：`tiny`，仅限英文

---

## 语言代码参考

常用语言代码（传给 `-l` 参数）：

| 语言 | 代码 |
|------|------|
| 中文 | `zh` |
| 英文 | `en` |
| 日文 | `ja` |
| 韩文 | `ko` |
| 法文 | `fr` |
| 德文 | `de` |
| 西班牙文 | `es` |

不指定语言时 whisper 会自动检测，small 及以上模型自动检测准确率较高。
