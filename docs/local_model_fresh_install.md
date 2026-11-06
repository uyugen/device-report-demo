# 从空环境部署本地 Qwen 写作服务

这是一条独立安装路径，不依赖学校服务器的 `/data1/tjb` 目录、GPU 5、模型清单或原有密钥。先完成[应用部署](deployment.md)，再在**自己分配的GPU**上准备模型。已有可用的兼容接口时可直接接入，无需重复部署模型。

## 资源与版本

采用 llama.cpp `b12065`，模型为社区提供的 Q4_K_M GGUF，不是官方BF16原权重。当前接入仅处理文本，不需要视觉投影文件，也没有使用图像诊断。

| 模型 | 权重文件大小 | 固定版本 | SHA256 |
| --- | --- | --- | --- |
| Qwen3.5-9B-Q4_K_M | 约5.68 GB | `3885219b6810b007914f3a7950a8d1b469d598a5` | `03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8` |
| Qwen3.5-27B-Q4_K_M | 16,740,812,704字节 | `3221f178a6b842d04f1fb42f1c413534adcc0a6a` | `84b5f7f112156d63836a01a69dc3f11a6ba63b10a23b8ca7a7efaf52d5a2d806` |

权重之外还需要KV缓存和计算空间。旧服务器27B单并发、65536上下文、q8缓存的单次验收显存峰值约17.8 GiB，不是所有显卡或输入下的上限。27B建议先准备至少28 GiB空闲显存用于启动和验证；9B也须留出缓存及计算空间，可先在有20 GiB以上空闲显存的卡上验收。资源不足时降低服务端和应用端的上下文并重新检查完整输入是否能容纳，或改用资源更充足的机器。独立命令不包含旧服务器的轮询保护，不构成显存硬配额。

模型目录建议另留30 GB以上磁盘给27B权重、源码和编译产物；9B可相应减少。CPU运行不需要CUDA但更慢，内存须覆盖权重、缓存和程序；先用GPU完成正式部署验收。

## 编译运行时

下面以Ubuntu和**已安装且兼容驱动的CUDA Toolkit**为前提。`nvidia-smi` 显示的CUDA版本是驱动能力，不代表已安装 `nvcc`；先运行 `nvcc --version`。不同系统按NVIDIA官方说明安装匹配版本，不为本Demo升级共享服务器驱动或系统GLIBC。

```bash
sudo apt-get install -y build-essential cmake git curl libcurl4-openssl-dev libssl-dev
mkdir -p "$HOME/device-report-model"
cd "$HOME/device-report-model"
git clone --branch b12065 --depth 1 https://github.com/ggml-org/llama.cpp.git
cmake -S llama.cpp -B llama.cpp/build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
cmake --build llama.cpp/build --config Release --target llama-server -j 8
./llama.cpp/build/bin/llama-server --version
mkdir -p models
```

这里仅引用用户自己的 `$HOME`，没有修改其值。CUDA不在默认搜索路径时，根据本机 `nvcc` 所在目录设置 `CUDACXX` 或 `CUDAToolkit_ROOT` 后重新配置。架构、工具链和共享库问题应根据本机报错处理，不能直接复制旧服务器编译目录。

## 下载并校验权重

27B：

```bash
curl --fail --location --retry 3 --output models/Qwen3.5-27B-Q4_K_M.gguf https://huggingface.co/unsloth/Qwen3.5-27B-GGUF/resolve/3221f178a6b842d04f1fb42f1c413534adcc0a6a/Qwen3.5-27B-Q4_K_M.gguf
echo '84b5f7f112156d63836a01a69dc3f11a6ba63b10a23b8ca7a7efaf52d5a2d806  models/Qwen3.5-27B-Q4_K_M.gguf' | sha256sum --check
```

9B：

```bash
curl --fail --location --retry 3 --output models/Qwen3.5-9B-Q4_K_M.gguf https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/3885219b6810b007914f3a7950a8d1b469d598a5/Qwen3.5-9B-Q4_K_M.gguf
echo '03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8  models/Qwen3.5-9B-Q4_K_M.gguf' | sha256sum --check
```

只下载选定模型即可。需要网络代理或镜像时使用部署方认可的方式，保持版本和文件哈希一致。下载错误页、未完成文件或其他量化规格不能通过上述校验。

## 启动模型接口

在上述模型目录生成自己的密钥，不打印或提交该文件：

```bash
umask 077
openssl rand -hex 32 > api-key
nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv
```

下面 `CUDA_VISIBLE_DEVICES=0` 只是**已确认分配GPU为0**的示例；按实际授权编号修改。命令在前台运行，按 Ctrl+C 退出，只启动一个模型即可：

```bash
CUDA_VISIBLE_DEVICES=0 ./llama.cpp/build/bin/llama-server \
  --model models/Qwen3.5-27B-Q4_K_M.gguf --alias Qwen3.5-27B-Q4_K_M \
  --host 127.0.0.1 --port 8057 --ctx-size 65536 --parallel 1 \
  --threads 8 --n-gpu-layers 99 --batch-size 512 --ubatch-size 128 \
  --cache-type-k q8_0 --cache-type-v q8_0 --flash-attn on --jinja \
  --chat-template-kwargs '{"enable_thinking":false}' --api-key-file api-key
```

9B替换 `--model`、`--alias` 为9B，对应端口可使用8058。应用只需要访问实际启动的端口；无需给本机浏览器转发模型端口。模型启动失败时查看当前终端的加载及CUDA日志，不停止其他任务腾显存。

## 连接报告应用

在应用目录编辑 `.env`，将 `MODEL_API_KEY` 设置为刚生成文件中的内容，不保留尖括号或示例文字：

```dotenv
LLM_ENABLED=true
MODEL_BASE_URL=http://127.0.0.1:8057/v1
MODEL_NAME=Qwen3.5-27B-Q4_K_M
MODEL_API_STYLE=llama_cpp
MODEL_CONTEXT_TOKENS=65536
MODEL_TIMEOUT_SECONDS=900
MODEL_API_KEY=填写本机新生成的密钥
```

9B按实际端口与别名填写。应用和模型在不同主机时，回环地址不通，应使用经过认证的内网连接或专用SSH隧道；不能直接开放无访问控制的模型接口。

重启应用后执行[模型自动验收](deployment.md#接入模型)。`writer.mode=llm` 且模型名正确才算写作调用通过；报告生成成功但回退固定说明不算模型验收成功。下载、编译、GPU可用性和模型写作是独立检查步骤，这份说明不声明已在每一种新机器上验证。

模型及推理引擎的许可条件以对应固定版本仓库为准：

- [Qwen3.5-9B 基座](https://huggingface.co/Qwen/Qwen3.5-9B)
- [Qwen3.5-27B 基座](https://huggingface.co/Qwen/Qwen3.5-27B)
- [9B量化固定版本](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/tree/3885219b6810b007914f3a7950a8d1b469d598a5)
- [27B量化固定版本](https://huggingface.co/unsloth/Qwen3.5-27B-GGUF/tree/3221f178a6b842d04f1fb42f1c413534adcc0a6a)
- [llama.cpp b12065](https://github.com/ggml-org/llama.cpp/tree/b12065)
