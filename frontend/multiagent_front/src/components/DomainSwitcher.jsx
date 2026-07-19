// 阶段48-21: Domain Switcher - 让用户能切换到其他业务场景 (HR/电商/教育)
// 拉 /v2/manifest 拿当前 domain + agents
// 后端 /v2/manifest/list 看可用 yaml
// 后端 /v2/manifest/switch 切换

import React, { useState, useEffect, useCallback } from "react";
import {
  Box,
  Chip,
  Menu,
  MenuItem,
  ListItemText,
  ListItemIcon,
  Button,
  Divider,
  Typography,
  CircularProgress,
} from "@mui/material";
import {
  Public as PublicIcon,
  Check as CheckIcon,
  Refresh as RefreshIcon,
} from "@mui/icons-material";

const API_BASE = import.meta?.env?.VITE_API_BASE || "http://localhost:13002";

const COLOR_BY_DOMAIN = {
  personal_health_assistant: "#1565C0",
  enterprise_assistant: "#6A1B9A",
  ecommerce_support: "#E65100",
  edu_tutor: "#2E7D32",
};

const COLOR_DEFAULT = "#37474F";

function getDomainColor(name = "") {
  return COLOR_BY_DOMAIN[name] || COLOR_DEFAULT;
}

export default function DomainSwitcher({ onDomainChange }) {
  const [manifest, setManifest] = useState(null); // current domain
  const [available, setAvailable] = useState([]); // available yaml
  const [anchor, setAnchor] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // 阶段48-21: 用 localStorage 的 token 拿 Authorization (匹配 NewChat.jsx 的其他 fetch)
  const getAuthHeader = () => {
    if (typeof window === "undefined") return "";
    const t = window.localStorage.getItem("access_token");
    return t ? `Bearer ${t}` : "";
  };

  const loadCurrent = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const r = await fetch(API_BASE + "/v2/manifest", {
        headers: { Authorization: getAuthHeader() },
      });
      if (!r.ok) throw new Error("GET /v2/manifest failed: " + r.status);
      const m = await r.json();
      setManifest(m);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  const loadAvailable = useCallback(async () => {
    try {
      const r = await fetch(API_BASE + "/v2/manifest/list", {
        headers: { Authorization: getAuthHeader() },
      });
      if (!r.ok) throw new Error("list failed");
      const data = await r.json();
      setAvailable(data.manifests || []);
    } catch (e) {
      console.warn("[DomainSwitcher] load available failed:", e);
    }
  }, []);

  useEffect(() => {
    loadCurrent();
    loadAvailable();
  }, [loadCurrent, loadAvailable]);

  const handleSwitch = async (name) => {
    setBusy(true);
    setError("");
    try {
      const r = await fetch(API_BASE + "/v2/manifest/switch", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: getAuthHeader(),
        },
        body: JSON.stringify({ name }),
      });
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error(data.detail || "switch failed");
      // Reload current
      await loadCurrent();
      onDomainChange?.();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
      setAnchor(null);
    }
  };

  if (!manifest) {
    return busy ? <CircularProgress size={20} /> : null;
  }

  const color = getDomainColor(manifest.domain_name);

  return (
    <Box sx={{ display: "inline-flex", alignItems: "center", gap: 1 }}>
      <Button
        size="small"
        startIcon={<PublicIcon />}
        onClick={(e) => setAnchor(e.currentTarget)}
        sx={{
          textTransform: "none",
          color,
          borderColor: color,
          fontWeight: 600,
        }}
        variant="outlined"
      >
        {manifest.display_name}
      </Button>
      <Menu
        anchorEl={anchor}
        open={!!anchor}
        onClose={() => setAnchor(null)}
        PaperProps={{ sx: { minWidth: 280, maxWidth: 380 } }}
      >
        <MenuItem disabled sx={{ opacity: 0.7 }}>
          <ListItemIcon>
            <PublicIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText
            primary="切换应用场景"
            secondary={`当前: ${manifest.display_name} · ${manifest.agents.length} agents`}
            primaryTypographyProps={{ variant: "subtitle2" }}
          />
        </MenuItem>
        <Divider />
        {available.map((m) => {
          const isCurrent = m.name === manifest.domain_name;
          const c = getDomainColor(m.name);
          return (
            <MenuItem
              key={m.file}
              onClick={() => !isCurrent && handleSwitch(m.name)}
              disabled={isCurrent || busy}
              sx={{ alignItems: "flex-start", py: 1 }}
            >
              <ListItemIcon sx={{ minWidth: 36 }}>
                {isCurrent ? (
                  <CheckIcon sx={{ color: c }} fontSize="small" />
                ) : (
                  <Box
                    sx={{
                      width: 14,
                      height: 14,
                      borderRadius: "50%",
                      bgcolor: c,
                      mt: 0.5,
                    }}
                  />
                )}
              </ListItemIcon>
              <ListItemText
                primary={
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                    <Typography sx={{ fontWeight: isCurrent ? 700 : 500 }}>
                      {m.display_name}
                    </Typography>
                    {m.name === manifest.domain_name && (
                      <Chip
                        label="当前"
                        size="small"
                        sx={{ height: 18, fontSize: "0.65rem" }}
                        color="primary"
                      />
                    )}
                  </Box>
                }
                secondary={`${m.agent_count} agents · host=${m.host_agent}`}
                secondaryTypographyProps={{ fontSize: "0.75rem" }}
              />
            </MenuItem>
          );
        })}
        <Divider />
        <MenuItem
          onClick={() => {
            loadCurrent();
            loadAvailable();
            setAnchor(null);
          }}
        >
          <ListItemIcon>
            <RefreshIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary="刷新 manifest" />
        </MenuItem>
      </Menu>
      {error && (
        <Typography variant="caption" color="error" sx={{ ml: 1 }}>
          {error}
        </Typography>
      )}
    </Box>
  );
}
