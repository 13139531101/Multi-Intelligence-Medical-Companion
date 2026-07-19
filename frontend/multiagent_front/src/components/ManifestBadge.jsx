// 阶段48-21: Manifest Badge - 显示当前 domain + agent 列表 + dangerously 标
// 用 /v2/manifest 拉取. supports dangerously: true 高危 agent 用 🔒 标.

import React, { useState, useEffect, useCallback } from "react";
import {
  Box,
  Chip,
  Stack,
  Tooltip,
  Typography,
  CircularProgress,
} from "@mui/material";
import {
  Lock as LockIcon,
  SmartToy as SmartToyIcon,
} from "@mui/icons-material";

const API_BASE = import.meta?.env?.VITE_API_BASE || "http://localhost:13002";

const PALETTE = [
  "#1565C0",
  "#00897B",
  "#7B1FA2",
  "#E65100",
  "#5D4037",
  "#C62828",
  "#283593",
  "#558B2F",
];

function getColor(name, idx) {
  // 简单 hash
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  return PALETTE[Math.abs(h) % PALETTE.length];
}

export default function ManifestBadge({ refreshKey = 0 }) {
  const [manifest, setManifest] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const getAuthHeader = () => {
    if (typeof window === "undefined") return "";
    const t = window.localStorage.getItem("access_token");
    return t ? `Bearer ${t}` : "";
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const r = await fetch(API_BASE + "/v2/manifest", {
        headers: { Authorization: getAuthHeader() },
      });
      if (!r.ok) throw new Error("manifest load failed: " + r.status);
      const m = await r.json();
      setManifest(m);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  if (loading) return <CircularProgress size={16} />;
  if (error) return <Chip label={error} size="small" color="error" />;
  if (!manifest) return null;

  return (
    <Stack
      direction="row"
      alignItems="center"
      spacing={1}
      sx={{ flexWrap: "wrap", gap: 0.5 }}
    >
      <Chip
        icon={<SmartToyIcon fontSize="small" />}
        label={manifest.display_name}
        size="small"
        color="primary"
        sx={{ fontWeight: 600 }}
      />
      {manifest.agents.map((a, i) => {
        const c = getColor(a.name, i);
        const isHost = a.name === manifest.host_agent;
        return (
          <Tooltip
            key={a.name}
            title={
              <Box>
                <Typography sx={{ fontWeight: 600 }}>
                  {a.display_name}
                </Typography>
                {a.description && (
                  <Typography variant="caption" sx={{ display: "block" }}>
                    {a.description}
                  </Typography>
                )}
                {a.dangerously && (
                  <Typography variant="caption" sx={{ color: "#FFAB91" }}>
                    🔒 HITL 必走 confirm
                  </Typography>
                )}
              </Box>
            }
          >
            <Chip
              size="small"
              label={
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                  {a.dangerously && <LockIcon sx={{ fontSize: 12 }} />}
                  {a.display_name}
                  {isHost && " •"}
                </Box>
              }
              sx={{
                bgcolor: c,
                color: "white",
                fontWeight: 500,
                fontSize: "0.7rem",
                height: 24,
              }}
            />
          </Tooltip>
        );
      })}
    </Stack>
  );
}
