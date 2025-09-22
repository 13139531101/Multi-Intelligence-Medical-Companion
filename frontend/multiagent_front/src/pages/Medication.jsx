import React, { useState, useEffect } from 'react';
import {
  Container,
  Grid,
  Card,
  CardContent,
  CardActions,
  Typography,
  Button,
  Box,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Chip,
  Avatar,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  ListItemSecondaryAction,
  IconButton,
  Switch,
  FormControlLabel,
  Alert,
  Tabs,
  Tab,
  Badge,
  Divider
} from '@mui/material';
import {
  Add,
  Medication as MedicationIcon,
  Schedule,
  Notifications,
  Edit,
  Delete,
  NotificationsActive,
  NotificationsOff,
  Warning,
  CheckCircle,
  AccessTime,
  CalendarToday,
  LocalPharmacy
} from '@mui/icons-material';
import { TimePicker } from '@mui/x-date-pickers/TimePicker';
import { DatePicker } from '@mui/x-date-pickers/DatePicker';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { AdapterDayjs } from '@mui/x-date-pickers/AdapterDayjs';
import dayjs from 'dayjs';
import Header from '../components/HealthHeader';
import AgentAssistant from '../components/AgentAssistant';
import { getMedications, addMedication, updateMedication, deleteMedication, getMedicationReminders } from '../api/healthApi';

const Medication = () => {
  const [medications, setMedications] = useState([]);
  const [reminders, setReminders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openDialog, setOpenDialog] = useState(false);
  const [editingMedication, setEditingMedication] = useState(null);
  const [tabValue, setTabValue] = useState(0);

  const [formData, setFormData] = useState({
    name: '',
    dosage: '',
    frequency: 'daily',
    times: [dayjs().hour(8).minute(0)],
    startDate: dayjs(),
    endDate: null,
    instructions: '',
    reminderEnabled: true,
    beforeMeal: false,
    withFood: false,
    notes: ''
  });

  const frequencies = [
    { value: 'daily', label: '每日', times: 1 },
    { value: 'twice_daily', label: '每日两次', times: 2 },
    { value: 'three_times_daily', label: '每日三次', times: 3 },
    { value: 'four_times_daily', label: '每日四次', times: 4 },
    { value: 'weekly', label: '每周', times: 1 },
    { value: 'as_needed', label: '按需服用', times: 0 }
  ];

  const medicationTypes = [
    { value: 'tablet', label: '片剂', icon: '💊' },
    { value: 'capsule', label: '胶囊', icon: '💊' },
    { value: 'liquid', label: '液体', icon: '🧪' },
    { value: 'injection', label: '注射', icon: '💉' },
    { value: 'cream', label: '外用药', icon: '🧴' },
    { value: 'inhaler', label: '吸入剂', icon: '🫁' }
  ];

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [medicationsData, remindersData] = await Promise.all([
        getMedications(),
        getMedicationReminders()
      ]);
      setMedications(medicationsData);
      setReminders(remindersData);
    } catch (error) {
      console.error('获取用药数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async () => {
    try {
      if (editingMedication) {
        await updateMedication(editingMedication.id, formData);
      } else {
        await addMedication(formData);
      }
      await fetchData();
      handleCloseDialog();
    } catch (error) {
      console.error('保存用药信息失败:', error);
    }
  };

  const handleDelete = async (id) => {
    if (window.confirm('确定要删除这个用药记录吗？')) {
      try {
        await deleteMedication(id);
        await fetchData();
      } catch (error) {
        console.error('删除用药记录失败:', error);
      }
    }
  };

  const handleOpenDialog = (medication = null) => {
    if (medication) {
      setEditingMedication(medication);
      setFormData({
        name: medication.name,
        dosage: medication.dosage,
        frequency: medication.frequency,
        times: medication.times.map(time => dayjs(time)),
        startDate: dayjs(medication.startDate),
        endDate: medication.endDate ? dayjs(medication.endDate) : null,
        instructions: medication.instructions,
        reminderEnabled: medication.reminderEnabled,
        beforeMeal: medication.beforeMeal,
        withFood: medication.withFood,
        notes: medication.notes
      });
    } else {
      setEditingMedication(null);
      setFormData({
        name: '',
        dosage: '',
        frequency: 'daily',
        times: [dayjs().hour(8).minute(0)],
        startDate: dayjs(),
        endDate: null,
        instructions: '',
        reminderEnabled: true,
        beforeMeal: false,
        withFood: false,
        notes: ''
      });
    }
    setOpenDialog(true);
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
    setEditingMedication(null);
  };

  const handleFrequencyChange = (frequency) => {
    const freqInfo = frequencies.find(f => f.value === frequency);
    const timesCount = freqInfo?.times || 1;
    
    let newTimes = [];
    if (timesCount === 1) {
      newTimes = [dayjs().hour(8).minute(0)];
    } else if (timesCount === 2) {
      newTimes = [
        dayjs().hour(8).minute(0),
        dayjs().hour(20).minute(0)
      ];
    } else if (timesCount === 3) {
      newTimes = [
        dayjs().hour(8).minute(0),
        dayjs().hour(14).minute(0),
        dayjs().hour(20).minute(0)
      ];
    } else if (timesCount === 4) {
      newTimes = [
        dayjs().hour(8).minute(0),
        dayjs().hour(12).minute(0),
        dayjs().hour(16).minute(0),
        dayjs().hour(20).minute(0)
      ];
    }
    
    setFormData(prev => ({
      ...prev,
      frequency,
      times: newTimes
    }));
  };

  const updateTime = (index, newTime) => {
    setFormData(prev => ({
      ...prev,
      times: prev.times.map((time, i) => i === index ? newTime : time)
    }));
  };

  const getTodayReminders = () => {
    const today = dayjs().format('YYYY-MM-DD');
    return reminders.filter(reminder => 
      dayjs(reminder.scheduledTime).format('YYYY-MM-DD') === today
    );
  };

  const getUpcomingReminders = () => {
    const now = dayjs();
    return reminders.filter(reminder => 
      dayjs(reminder.scheduledTime).isAfter(now) &&
      dayjs(reminder.scheduledTime).diff(now, 'hours') <= 24
    );
  };

  const getOverdueReminders = () => {
    const now = dayjs();
    return reminders.filter(reminder => 
      dayjs(reminder.scheduledTime).isBefore(now) && !reminder.taken
    );
  };

  const activeMedications = medications.filter(med => {
    const now = dayjs();
    const startDate = dayjs(med.startDate);
    const endDate = med.endDate ? dayjs(med.endDate) : null;
    return now.isAfter(startDate) && (!endDate || now.isBefore(endDate));
  });

  const todayReminders = getTodayReminders();
  const upcomingReminders = getUpcomingReminders();
  const overdueReminders = getOverdueReminders();

  return (
    <LocalizationProvider dateAdapter={AdapterDayjs}>
      <Box sx={{ flexGrow: 1, bgcolor: '#f5f5f5', minHeight: '100vh' }}>
        <Header />
        <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
          {/* 页面标题和操作 */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
            <Typography variant="h4" gutterBottom>
              用药管理
            </Typography>
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => handleOpenDialog()}
              sx={{ borderRadius: 2 }}
            >
              添加药物
            </Button>
          </Box>

          {/* 提醒统计 */}
          <Grid container spacing={3} sx={{ mb: 3 }}>
            <Grid item xs={12} md={4}>
              <Card sx={{ bgcolor: overdueReminders.length > 0 ? 'error.light' : 'success.light' }}>
                <CardContent sx={{ textAlign: 'center' }}>
                  <Badge badgeContent={overdueReminders.length} color="error">
                    <Warning sx={{ fontSize: 40, color: 'white', mb: 1 }} />
                  </Badge>
                  <Typography variant="h6" color="white">
                    {overdueReminders.length > 0 ? '有逾期用药' : '按时用药'}
                  </Typography>
                  <Typography variant="body2" color="white">
                    {overdueReminders.length} 个逾期提醒
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={4}>
              <Card sx={{ bgcolor: 'info.light' }}>
                <CardContent sx={{ textAlign: 'center' }}>
                  <Badge badgeContent={todayReminders.length} color="primary">
                    <CalendarToday sx={{ fontSize: 40, color: 'white', mb: 1 }} />
                  </Badge>
                  <Typography variant="h6" color="white">
                    今日用药
                  </Typography>
                  <Typography variant="body2" color="white">
                    {todayReminders.length} 次用药
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={4}>
              <Card sx={{ bgcolor: 'warning.light' }}>
                <CardContent sx={{ textAlign: 'center' }}>
                  <Badge badgeContent={upcomingReminders.length} color="warning">
                    <AccessTime sx={{ fontSize: 40, color: 'white', mb: 1 }} />
                  </Badge>
                  <Typography variant="h6" color="white">
                    即将到时
                  </Typography>
                  <Typography variant="body2" color="white">
                    {upcomingReminders.length} 个提醒
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          {/* 标签页 */}
          <Tabs value={tabValue} onChange={(e, v) => setTabValue(v)} sx={{ mb: 2 }}>
            <Tab label={`当前用药 (${activeMedications.length})`} />
            <Tab label={`今日提醒 (${todayReminders.length})`} />
            <Tab label="用药历史" />
          </Tabs>

          {/* 当前用药 */}
          {tabValue === 0 && (
            <Grid container spacing={3}>
              {activeMedications.length === 0 ? (
                <Grid item xs={12}>
                  <Alert severity="info">
                    暂无当前用药记录
                  </Alert>
                </Grid>
              ) : (
                activeMedications.map((medication) => (
                  <Grid item xs={12} md={6} key={medication.id}>
                    <Card>
                      <CardContent>
                        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                          <Avatar sx={{ bgcolor: 'primary.main', mr: 2 }}>
                            <MedicationIcon />
                          </Avatar>
                          <Box sx={{ flexGrow: 1 }}>
                            <Typography variant="h6">
                              {medication.name}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              {medication.dosage}
                            </Typography>
                          </Box>
                          <Box sx={{ textAlign: 'right' }}>
                            <Chip
                              icon={medication.reminderEnabled ? <NotificationsActive /> : <NotificationsOff />}
                              label={medication.reminderEnabled ? '提醒开启' : '提醒关闭'}
                              size="small"
                              color={medication.reminderEnabled ? 'success' : 'default'}
                            />
                          </Box>
                        </Box>
                        
                        <Typography variant="body2" sx={{ mb: 1 }}>
                          <strong>频次：</strong>{frequencies.find(f => f.value === medication.frequency)?.label}
                        </Typography>
                        
                        <Typography variant="body2" sx={{ mb: 1 }}>
                          <strong>用药时间：</strong>
                          {medication.times.map((time, index) => (
                            <Chip
                              key={index}
                              label={dayjs(time).format('HH:mm')}
                              size="small"
                              sx={{ ml: 0.5 }}
                            />
                          ))}
                        </Typography>
                        
                        <Typography variant="body2" sx={{ mb: 1 }}>
                          <strong>用药期间：</strong>
                          {dayjs(medication.startDate).format('MM/DD')} - 
                          {medication.endDate ? dayjs(medication.endDate).format('MM/DD') : '长期'}
                        </Typography>
                        
                        {medication.instructions && (
                          <Typography variant="body2" sx={{ mb: 1 }}>
                            <strong>用法：</strong>{medication.instructions}
                          </Typography>
                        )}
                        
                        <Box sx={{ mt: 2 }}>
                          {medication.beforeMeal && (
                            <Chip label="饭前服用" size="small" sx={{ mr: 1 }} />
                          )}
                          {medication.withFood && (
                            <Chip label="随餐服用" size="small" sx={{ mr: 1 }} />
                          )}
                        </Box>
                      </CardContent>
                      <CardActions>
                        <IconButton size="small" onClick={() => handleOpenDialog(medication)}>
                          <Edit />
                        </IconButton>
                        <IconButton size="small" onClick={() => handleDelete(medication.id)}>
                          <Delete />
                        </IconButton>
                      </CardActions>
                    </Card>
                  </Grid>
                ))
              )}
            </Grid>
          )}

          {/* 今日提醒 */}
          {tabValue === 1 && (
            <Card>
              <CardContent>
                <List>
                  {todayReminders.length === 0 ? (
                    <Alert severity="info">
                      今日暂无用药提醒
                    </Alert>
                  ) : (
                    todayReminders.map((reminder, index) => {
                      const isOverdue = dayjs(reminder.scheduledTime).isBefore(dayjs());
                      const medication = medications.find(m => m.id === reminder.medicationId);
                      
                      return (
                        <React.Fragment key={reminder.id}>
                          <ListItem>
                            <ListItemAvatar>
                              <Avatar sx={{
                                bgcolor: reminder.taken ? 'success.main' : 
                                        isOverdue ? 'error.main' : 'warning.main'
                              }}>
                                {reminder.taken ? <CheckCircle /> : 
                                 isOverdue ? <Warning /> : <Schedule />}
                              </Avatar>
                            </ListItemAvatar>
                            <ListItemText
                              primary={
                                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                                  <Typography variant="body1" sx={{ mr: 1 }}>
                                    {medication?.name}
                                  </Typography>
                                  <Chip
                                    label={dayjs(reminder.scheduledTime).format('HH:mm')}
                                    size="small"
                                    color={reminder.taken ? 'success' : isOverdue ? 'error' : 'warning'}
                                  />
                                </Box>
                              }
                              secondary={
                                <Box>
                                  <Typography variant="body2">
                                    {medication?.dosage}
                                  </Typography>
                                  <Typography variant="caption" color={
                                    reminder.taken ? 'success.main' : 
                                    isOverdue ? 'error.main' : 'text.secondary'
                                  }>
                                    {reminder.taken ? '已服用' : 
                                     isOverdue ? '逾期未服用' : '待服用'}
                                  </Typography>
                                </Box>
                              }
                            />
                            <ListItemSecondaryAction>
                              {!reminder.taken && (
                                <Button
                                  size="small"
                                  variant="contained"
                                  color="success"
                                  onClick={() => {
                                    // 标记为已服用的逻辑
                                  }}
                                >
                                  已服用
                                </Button>
                              )}
                            </ListItemSecondaryAction>
                          </ListItem>
                          {index < todayReminders.length - 1 && <Divider />}
                        </React.Fragment>
                      );
                    })
                  )}
                </List>
              </CardContent>
            </Card>
          )}

          {/* 用药历史 */}
          {tabValue === 2 && (
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  用药历史记录
                </Typography>
                <List>
                  {medications.map((medication) => {
                    const isActive = activeMedications.includes(medication);
                    return (
                      <ListItem key={medication.id} divider>
                        <ListItemAvatar>
                          <Avatar sx={{ bgcolor: isActive ? 'success.main' : 'grey.500' }}>
                            <MedicationIcon />
                          </Avatar>
                        </ListItemAvatar>
                        <ListItemText
                          primary={medication.name}
                          secondary={
                            <Box>
                              <Typography variant="body2">
                                {medication.dosage} • {frequencies.find(f => f.value === medication.frequency)?.label}
                              </Typography>
                              <Typography variant="caption">
                                {dayjs(medication.startDate).format('YYYY/MM/DD')} - 
                                {medication.endDate ? dayjs(medication.endDate).format('YYYY/MM/DD') : '长期'}
                              </Typography>
                            </Box>
                          }
                        />
                        <ListItemSecondaryAction>
                          <Chip
                            label={isActive ? '进行中' : '已结束'}
                            size="small"
                            color={isActive ? 'success' : 'default'}
                          />
                        </ListItemSecondaryAction>
                      </ListItem>
                    );
                  })}
                </List>
              </CardContent>
            </Card>
          )}
        </Container>

        {/* 添加/编辑对话框 */}
        <Dialog open={openDialog} onClose={handleCloseDialog} maxWidth="md" fullWidth>
          <DialogTitle>
            {editingMedication ? '编辑用药信息' : '添加用药信息'}
          </DialogTitle>
          <DialogContent>
            <Grid container spacing={2} sx={{ mt: 1 }}>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="药物名称"
                  value={formData.name}
                  onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="剂量"
                  value={formData.dosage}
                  onChange={(e) => setFormData(prev => ({ ...prev, dosage: e.target.value }))}
                  placeholder="例如：1片、5ml、100mg"
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <FormControl fullWidth>
                  <InputLabel>服用频次</InputLabel>
                  <Select
                    value={formData.frequency}
                    label="服用频次"
                    onChange={(e) => handleFrequencyChange(e.target.value)}
                  >
                    {frequencies.map(freq => (
                      <MenuItem key={freq.value} value={freq.value}>
                        {freq.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} md={6}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={formData.reminderEnabled}
                      onChange={(e) => setFormData(prev => ({ ...prev, reminderEnabled: e.target.checked }))}
                    />
                  }
                  label="启用提醒"
                />
              </Grid>
              
              {/* 用药时间 */}
              {formData.frequency !== 'as_needed' && (
                <Grid item xs={12}>
                  <Typography variant="subtitle2" gutterBottom>
                    用药时间：
                  </Typography>
                  <Grid container spacing={2}>
                    {formData.times.map((time, index) => (
                      <Grid item xs={6} md={3} key={index}>
                        <TimePicker
                          label={`第${index + 1}次`}
                          value={time}
                          onChange={(newTime) => updateTime(index, newTime)}
                          renderInput={(params) => <TextField {...params} fullWidth />}
                        />
                      </Grid>
                    ))}
                  </Grid>
                </Grid>
              )}
              
              <Grid item xs={12} md={6}>
                <DatePicker
                  label="开始日期"
                  value={formData.startDate}
                  onChange={(date) => setFormData(prev => ({ ...prev, startDate: date }))}
                  renderInput={(params) => <TextField {...params} fullWidth />}
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <DatePicker
                  label="结束日期（可选）"
                  value={formData.endDate}
                  onChange={(date) => setFormData(prev => ({ ...prev, endDate: date }))}
                  renderInput={(params) => <TextField {...params} fullWidth />}
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="用法说明"
                  value={formData.instructions}
                  onChange={(e) => setFormData(prev => ({ ...prev, instructions: e.target.value }))}
                  placeholder="例如：口服、外用、注射等"
                />
              </Grid>
              
              <Grid item xs={12} md={6}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={formData.beforeMeal}
                      onChange={(e) => setFormData(prev => ({ ...prev, beforeMeal: e.target.checked }))}
                    />
                  }
                  label="饭前服用"
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={formData.withFood}
                      onChange={(e) => setFormData(prev => ({ ...prev, withFood: e.target.checked }))}
                    />
                  }
                  label="随餐服用"
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  multiline
                  rows={3}
                  label="备注"
                  value={formData.notes}
                  onChange={(e) => setFormData(prev => ({ ...prev, notes: e.target.value }))}
                  placeholder="其他注意事项..."
                />
              </Grid>
            </Grid>
          </DialogContent>
          <DialogActions>
            <Button onClick={handleCloseDialog}>取消</Button>
            <Button onClick={handleSubmit} variant="contained">
              {editingMedication ? '更新' : '添加'}
            </Button>
          </DialogActions>
        </Dialog>
        
        {/* 智能助手 */}
        <AgentAssistant 
          agentType="medication"
          contextPrompt="当前用户正在使用用药管理页面，可能需要关于药物管理、用药提醒、药物相互作用等方面的帮助。"
          position="bottom-right"
          size="medium"
        />
      </Box>
    </LocalizationProvider>
  );
};

export default Medication;