# 时间标签的宽松写法

[社区整理](https://github.com/TriM-Organization/Lyric/blob/master/docs/Lrc%E6%96%87%E4%BB%B6%E6%A0%BC%E5%BC%8F.md)
列出的、真实文件在用的写法，本库全部接受：

```text
[mm:ss.fff]  [mm:ss.xx]  [hh:mm:ss]  [hh:mm:ss.fff]  [hh:mm:ss.xx]  [mm:ss]
[mm:ss.xx][mm:ss.xx][mm:ss.xx]重复出现的歌词
```

本库的处理：尾数 1-6 位（按位数补齐或截断到毫秒）、分钟 1-4 位、秒数越界
（`[00:99.000]`）按字面折算并告警、标签内的空白容忍。

语料里实际只出现 2 位（39266）与 3 位（547427）尾数，见 [corpus.md](corpus.md)。
