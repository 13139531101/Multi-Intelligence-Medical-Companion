// 阶段45: PHA theme. 医疗专业色，少渐变，无 emoji 强调。
import { createTheme } from "@mui/material/styles";

const theme = createTheme({
  palette: {
    mode: "light",
    primary: {
      main: "#1565C0",
      light: "#5E92F3",
      dark: "#003C8F",
      contrastText: "#FFFFFF",
    },
    secondary: {
      main: "#00897B",
      light: "#4EBAAA",
      dark: "#005B4F",
      contrastText: "#FFFFFF",
    },
    success: { main: "#2E7D32" },
    warning: { main: "#ED6C02" },
    error: { main: "#C62828" },
    info: { main: "#0277BD" },
    background: {
      default: "#F5F7FA",
      paper: "#FFFFFF",
    },
    text: {
      primary: "#1A2532",
      secondary: "#5A6776",
    },
    divider: "#E4E9EF",
  },
  typography: {
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Roboto", sans-serif',
    h1: { fontSize: "2rem", fontWeight: 600, letterSpacing: "-0.01em" },
    h2: { fontSize: "1.625rem", fontWeight: 600 },
    h3: { fontSize: "1.375rem", fontWeight: 600 },
    h4: { fontSize: "1.125rem", fontWeight: 600 },
    h5: { fontSize: "1rem", fontWeight: 600 },
    h6: { fontSize: "0.9375rem", fontWeight: 600 },
    body1: { fontSize: "0.9375rem", lineHeight: 1.6 },
    body2: { fontSize: "0.875rem", lineHeight: 1.6 },
    caption: { fontSize: "0.75rem", color: "#6B7785" },
    button: { textTransform: "none", fontWeight: 500 },
  },
  shape: {
    borderRadius: 6,
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: "none",
          fontWeight: 500,
          borderRadius: 6,
          padding: "6px 16px",
          boxShadow: "none",
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          border: "1px solid #E4E9EF",
          boxShadow: "none",
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          boxShadow: "none",
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          fontWeight: 500,
          borderRadius: 4,
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: "#FFFFFF",
          color: "#1A2532",
          boxShadow: "0 1px 0 #E4E9EF",
          borderBottom: "1px solid #E4E9EF",
        },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          height: 6,
          borderRadius: 3,
          backgroundColor: "#EEF1F5",
        },
      },
    },
  },
});

export default theme;
