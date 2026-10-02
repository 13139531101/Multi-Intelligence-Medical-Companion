/**
 * AiInfoCardView — AI 通过 page_update 投递到页面的信息卡片
 *
 * 为什么抽出来
 * ------------
 * 后端四个工具（用药概览 / 就诊摘要 / 档案历史 / 今日提醒）都会发
 * `component: "AiInfoCard", action: "setData"`。这张卡片的渲染原本只内联在
 * TodayDashboard 里，于是那些事件落到 Dashboard 上时无处可去。
 *
 * 抽成独立组件后，两个页面共用同一份渲染逻辑，也就不用把 130 行 JSX 抄第二遍。
 * 注意别和 pageContract 里的注册名 `AiInfoCard` 混淆：那是注册表的 key（字符串），
 * 这是渲染用的 React 组件。
 */

import React from "react";
import { Box, Paper, Stack, Typography, Chip, IconButton } from "@mui/material";
import { SmartToy, Close } from "@mui/icons-material";

export default function AiInfoCardView({ data, onClose }) {
  if (!data) return null;

  return (
    <Paper
      sx={{
        p: 2.5,
        borderRadius: 3,
        border: "2px solid",
        borderColor: "info.main",
        bgcolor: "rgba(0, 145, 234, 0.08)",
        position: "relative",
      }}
    >
      <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 1 }}>
        <Box
          sx={{
            width: 40,
            height: 40,
            borderRadius: "50%",
            bgcolor: "info.main",
            color: "white",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <SmartToy />
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="h6" sx={{ fontWeight: 600 }}>
            AI 分析结果
          </Typography>
          {data.title && (
            <Typography variant="body2" color="text.secondary">
              {data.title}
            </Typography>
          )}
        </Box>
        {onClose && (
          <IconButton size="small" onClick={onClose} aria-label="关闭">
            <Close fontSize="small" />
          </IconButton>
        )}
      </Stack>

      {/* 档案列表 */}
      {data.type === "health_records" && data.records && (
        <Box sx={{ mt: 1 }}>
          <Typography variant="body2" sx={{ mb: 1 }}>
            共 {data.records.length} 条记录
          </Typography>
          {data.records.slice(0, 3).map((r, i) => (
            <Chip
              key={i}
              label={r.name || r.date || `记录 ${i + 1}`}
              size="small"
              sx={{ mr: 0.5, mb: 0.5 }}
            />
          ))}
          {data.records.length > 3 && (
            <Typography variant="caption" color="text.secondary">
              ... 还有 {data.records.length - 3} 条
            </Typography>
          )}
        </Box>
      )}

      {/* 用药 */}
      {data.type === "medications" && data.medications && (
        <Box sx={{ mt: 1 }}>
          <Typography variant="body2" sx={{ mb: 1 }}>
            当前用药 {data.medications.length} 种
          </Typography>
          {data.medications.map((m, i) => (
            <Chip
              key={i}
              label={`${m.name} ${m.dose || ""}`}
              size="small"
              color="primary"
              sx={{ mr: 0.5, mb: 0.5 }}
            />
          ))}
        </Box>
      )}

      {/* 就诊摘要 — a2a_integration_tool.get_visit_summary_overview 产出的
          params 是 {type:'visit_summaries', summaries:[{date,summary,doctor}]}，
          此前没有对应分支，这类 page_update 到达后只剩 title/summary 文本。 */}
      {data.type === "visit_summaries" && data.summaries && (
        <Box sx={{ mt: 1 }}>
          <Typography variant="body2" sx={{ mb: 1 }}>
            共 {data.summaries.length} 条就诊记录
          </Typography>
          <Stack spacing={0.75}>
            {data.summaries.slice(0, 5).map((s, i) => (
              <Box
                key={i}
                sx={{
                  p: 1,
                  borderRadius: 1.5,
                  bgcolor: "background.paper",
                  border: "1px solid",
                  borderColor: "divider",
                }}
              >
                <Stack direction="row" spacing={1} alignItems="center">
                  <Chip
                    label={s.date || `第 ${i + 1} 次`}
                    size="small"
                    color="info"
                  />
                  {s.doctor && (
                    <Typography variant="caption" color="text.secondary">
                      {s.doctor}
                    </Typography>
                  )}
                </Stack>
                {s.summary && (
                  <Typography variant="body2" sx={{ mt: 0.5 }}>
                    {s.summary}
                  </Typography>
                )}
              </Box>
            ))}
            {data.summaries.length > 5 && (
              <Typography variant="caption" color="text.secondary">
                ... 还有 {data.summaries.length - 5} 条
              </Typography>
            )}
          </Stack>
        </Box>
      )}

      {data.summary && (
        <Typography variant="body2" sx={{ mt: 1 }}>
          {data.summary}
        </Typography>
      )}
    </Paper>
  );
}
