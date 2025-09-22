import React from 'react';
import {
  Snackbar,
  Alert,
  AlertTitle,
  Slide,
  IconButton
} from '@mui/material';
import { Close } from '@mui/icons-material';
import { useRecoilState } from 'recoil';
import { notificationState } from '../store/recoilState';

function SlideTransition(props) {
  return <Slide {...props} direction="up" />;
}

const NotificationSnackbar = () => {
  const [notification, setNotification] = useRecoilState(notificationState);

  const handleClose = (event, reason) => {
    if (reason === 'clickaway') {
      return;
    }
    setNotification(prev => ({ ...prev, open: false }));
  };

  const getSeverityConfig = (severity) => {
    const configs = {
      success: {
        title: '成功',
        color: 'success'
      },
      error: {
        title: '错误',
        color: 'error'
      },
      warning: {
        title: '警告',
        color: 'warning'
      },
      info: {
        title: '信息',
        color: 'info'
      }
    };
    return configs[severity] || configs.info;
  };

  const config = getSeverityConfig(notification.severity);

  return (
    <Snackbar
      open={notification.open}
      autoHideDuration={6000}
      onClose={handleClose}
      TransitionComponent={SlideTransition}
      anchorOrigin={{ vertical: 'top', horizontal: 'right' }}
      sx={{
        mt: 8, // 避免被Header遮挡
      }}
    >
      <Alert
        onClose={handleClose}
        severity={config.color}
        variant="filled"
        sx={{
          width: '100%',
          minWidth: 300,
          maxWidth: 500,
        }}
        action={
          <IconButton
            size="small"
            aria-label="close"
            color="inherit"
            onClick={handleClose}
          >
            <Close fontSize="small" />
          </IconButton>
        }
      >
        <AlertTitle>{config.title}</AlertTitle>
        {notification.message}
      </Alert>
    </Snackbar>
  );
};

export default NotificationSnackbar;