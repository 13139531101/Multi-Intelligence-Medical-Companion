import React, { useState, useEffect } from "react";
import {
  AppBar,
  Toolbar,
  Typography,
  Button,
  IconButton,
  Menu,
  MenuItem,
  Avatar,
  Box,
  Badge,
  Tooltip,
  Divider,
} from "@mui/material";
import {
  AccountCircle,
  Notifications,
  Settings,
  Logout,
  HealthAndSafety,
  Dashboard,
  FolderOpen,
  Chat,
  Medication,
  Assignment,
} from "@mui/icons-material";
import { useNavigate, useLocation } from "react-router-dom";
import { useRecoilValue, useSetRecoilState } from "recoil";
import { userState } from "../store/recoilState";
import { useAuth } from "../contexts/AuthContext";
import { getMedicationReminders } from "../api/healthApi";

const HealthHeader = () => {
  const [anchorEl, setAnchorEl] = useState(null);
  const [notificationAnchor, setNotificationAnchor] = useState(null);
  const [realNotifications, setRealNotifications] = useState([]);
  const navigate = useNavigate();
  const location = useLocation();
  const recoilUser = useRecoilValue(userState);
  const setRecoilUser = useSetRecoilState(userState);
  const { user: authUser, logout: authLogout, isAuthenticated } = useAuth();
  const user = authUser || recoilUser;

  useEffect(() => {
    if (!isAuthenticated) return;
    // 阶段48-6: 从 medication_reminders 拉真实数据
    (async () => {
      try {
        const list = await getMedicationReminders({ today: true });
        const arr = Array.isArray(list) ? list : list?.reminders || [];
        const pending = arr
          .filter((m) => !m.taken && m.status !== "taken")
          .slice(0, 5);
        setRealNotifications(
          pending.map((m, i) => ({
            id: `pending_${i}`,
            title: `服药提醒 · ${m.time || ""}`,
            message: `${m.drug_name || m.name || "药品"} ${m.dosage || m.dose || ""}`,
            time: "待服用",
            unread: true,
            action: () => navigate("/v2/medication"),
          })),
        );
      } catch (e) {
        /* ignore */
      }
    })();
  }, [isAuthenticated]);

  const handleProfileMenuOpen = (event) => {
    setAnchorEl(event.currentTarget);
  };

  const handleMenuClose = () => {
    setAnchorEl(null);
  };

  const handleNotificationOpen = (event) => {
    setNotificationAnchor(event.currentTarget);
  };

  const handleNotificationClose = () => {
    setNotificationAnchor(null);
  };

  const handleLogout = () => {
    // 使用认证上下文的登出功能
    authLogout();
    setRecoilUser(null);
    navigate("/login");
    handleMenuClose();
  };

  const navigationItems = [
    {
      label: "仪表板",
      path: "/v2/dashboard",
      icon: <Dashboard />,
    },
    {
      label: "健康档案",
      path: "/v2/health-records",
      icon: <FolderOpen />,
    },
    {
      label: "健康咨询",
      path: "/v2/chat",
      icon: <Chat />,
    },
    {
      label: "用药管理",
      path: "/v2/medication",
      icon: <Medication />,
    },
    {
      label: "就诊摘要",
      path: "/summary",
      icon: <Assignment />,
    },
  ];

  const mockNotifications = []; // 阶段48-6: 改用真实数据
  const unreadCount = realNotifications.filter((n) => n.unread).length;

  return (
    <AppBar
      position="static"
      sx={{ bgcolor: "primary.light", color: "primary.contrastText" }}
    >
      <Toolbar>
        {/* Logo和标题 */}
        <Box sx={{ display: "flex", alignItems: "center", flexGrow: 0, mr: 4 }}>
          <HealthAndSafety sx={{ mr: 1, fontSize: 28 }} />
          <Typography
            variant="h6"
            component="div"
            sx={{ fontWeight: "bold", color: "#FFFFFF", cursor: "pointer" }}
            onClick={() => navigate("/v2/dashboard")}
          >
            智能健康助手
          </Typography>
        </Box>

        {/* 导航菜单 */}
        <Box sx={{ flexGrow: 1, display: { xs: "none", md: "flex" } }}>
          {navigationItems.map((item) => {
            const isActive = location.pathname === item.path;
            return (
              <Button
                key={item.path}
                color="inherit"
                startIcon={item.icon}
                onClick={() => navigate(item.path)}
                sx={{
                  mx: 1,
                  borderRadius: 2,
                  color: "#FFFFFF",
                  fontWeight: 600,
                  bgcolor: isActive ? "rgba(255,255,255,0.2)" : "transparent",
                  "&:hover": {
                    bgcolor: "rgba(255,255,255,0.2)",
                  },
                }}
              >
                {item.label}
              </Button>
            );
          })}
        </Box>

        {/* 右侧操作区 */}
        <Box sx={{ display: "flex", alignItems: "center" }}>
          {/* 通知 */}
          <Tooltip title="通知">
            <IconButton
              color="inherit"
              onClick={handleNotificationOpen}
              sx={{ mr: 1 }}
            >
              <Badge badgeContent={unreadCount} color="error">
                <Notifications />
              </Badge>
            </IconButton>
          </Tooltip>

          {/* 用户菜单 */}
          <Box sx={{ display: "flex", alignItems: "center" }}>
            <Typography
              variant="body2"
              sx={{
                mr: 1,
                color: "#FFFFFF",
                display: { xs: "none", sm: "block" },
              }}
            >
              {user?.username || "用户"}
            </Typography>
            <IconButton color="inherit" onClick={handleProfileMenuOpen}>
              <Avatar sx={{ width: 32, height: 32, bgcolor: "secondary.main" }}>
                {user?.username?.charAt(0)?.toUpperCase() || "U"}
              </Avatar>
            </IconButton>
          </Box>
        </Box>
      </Toolbar>

      {/* 用户菜单 */}
      <Menu
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={handleMenuClose}
        onClick={handleMenuClose}
        PaperProps={{
          elevation: 0,
          sx: {
            overflow: "visible",
            filter: "drop-shadow(0px 2px 8px rgba(0,0,0,0.32))",
            mt: 1.5,
            "& .MuiAvatar-root": {
              width: 32,
              height: 32,
              ml: -0.5,
              mr: 1,
            },
            "&:before": {
              content: '""',
              display: "block",
              position: "absolute",
              top: 0,
              right: 14,
              width: 10,
              height: 10,
              bgcolor: "background.paper",
              transform: "translateY(-50%) rotate(45deg)",
              zIndex: 0,
            },
          },
        }}
        transformOrigin={{ horizontal: "right", vertical: "top" }}
        anchorOrigin={{ horizontal: "right", vertical: "bottom" }}
      >
        <MenuItem onClick={() => navigate("/profile")}>
          <Avatar sx={{ bgcolor: "primary.main" }}>
            <AccountCircle />
          </Avatar>
          个人资料
        </MenuItem>
        <MenuItem onClick={() => navigate("/settings")}>
          <Avatar sx={{ bgcolor: "grey.500" }}>
            <Settings />
          </Avatar>
          设置
        </MenuItem>
        <Divider />
        <MenuItem onClick={handleLogout}>
          <Avatar sx={{ bgcolor: "error.main" }}>
            <Logout />
          </Avatar>
          退出登录
        </MenuItem>
      </Menu>

      {/* 通知菜单 */}
      <Menu
        anchorEl={notificationAnchor}
        open={Boolean(notificationAnchor)}
        onClose={handleNotificationClose}
        PaperProps={{
          elevation: 0,
          sx: {
            overflow: "visible",
            filter: "drop-shadow(0px 2px 8px rgba(0,0,0,0.32))",
            mt: 1.5,
            minWidth: 300,
            maxWidth: 400,
            "&:before": {
              content: '""',
              display: "block",
              position: "absolute",
              top: 0,
              right: 14,
              width: 10,
              height: 10,
              bgcolor: "background.paper",
              transform: "translateY(-50%) rotate(45deg)",
              zIndex: 0,
            },
          },
        }}
        transformOrigin={{ horizontal: "right", vertical: "top" }}
        anchorOrigin={{ horizontal: "right", vertical: "bottom" }}
      >
        <Box sx={{ p: 2, borderBottom: 1, borderColor: "divider" }}>
          <Typography variant="h6">通知</Typography>
        </Box>
        {(realNotifications.length ? realNotifications : mockNotifications).map(
          (notification) => (
            <MenuItem
              key={notification.id}
              onClick={() => {
                if (notification.action) notification.action();
                handleNotificationClose();
              }}
              sx={{
                whiteSpace: "normal",
                alignItems: "flex-start",
                py: 1.5,
                bgcolor: notification.unread ? "action.hover" : "transparent",
                cursor: notification.action ? "pointer" : "default",
              }}
            >
              <Box sx={{ width: "100%" }}>
                <Box
                  sx={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    mb: 0.5,
                  }}
                >
                  <Typography
                    variant="subtitle2"
                    sx={{ fontWeight: notification.unread ? "bold" : "normal" }}
                  >
                    {notification.title}
                  </Typography>
                  {notification.unread && (
                    <Box
                      sx={{
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        bgcolor: "primary.main",
                      }}
                    />
                  )}
                </Box>
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ mb: 0.5 }}
                >
                  {notification.message}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {notification.time}
                </Typography>
              </Box>
            </MenuItem>
          ),
        )}
        <Divider />
        <MenuItem
          onClick={handleNotificationClose}
          sx={{ justifyContent: "center" }}
        >
          <Typography variant="body2" color="primary">
            查看全部通知
          </Typography>
        </MenuItem>
      </Menu>
    </AppBar>
  );
};

export default HealthHeader;
