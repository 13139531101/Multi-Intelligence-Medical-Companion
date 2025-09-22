import React, { useState, useEffect, useCallback } from 'react';
import { useRecoilValue, useSetRecoilState, useRecoilCallback } from 'recoil';
import {
    currentConversationIdState,
    completedFormsState,
    formResponsesState,
    messagesState,
    backgroundTasksState
} from '../store/recoilState';
import * as api from '../api/api';
import { v4 as uuidv4 } from 'uuid';
import ReactMarkdown from 'react-markdown';

// 引入 MUI 组件
import { TextField, Button, Card, CardContent, Typography, Alert, Stack, FormHelperText } from '@mui/material';

// 解析表单结构 (保持不变)
const parseFormElements = (message) => {
    const formPart = message.content?.find(part => part[1] === 'form');
    const formInfo = formPart?.[0];

    if (!formInfo || typeof formInfo !== 'object' || !formInfo.form?.properties) {
        return { instructions: '', elements: [] };
    }

    const properties = formInfo.form.properties;
    const requiredFields = formInfo.form.required || [];
    const initialData = formInfo.form_data || {};
    const instructions = formInfo.instructions || '';

    const elements = Object.entries(properties).map(([key, info]) => ({
        name: key,
        label: info.title || key,
        value: initialData[key] || info.default || '',
        formType: info.format || info.type || 'text',
        required: requiredFields.includes(key),
        formDetails: info,
    }));

    return { instructions, elements };
};

const FormRenderer = ({ message }) => {
    const currentConversationId = useRecoilValue(currentConversationIdState);
    const [completedForms, setCompletedForms] = useRecoilState(completedFormsState);
    const setFormResponse = useSetRecoilState(formResponsesState);
    const setMessages = useSetRecoilState(messagesState);
    const setBackgroundTasks = useSetRecoilState(backgroundTasksState);

    const formMessageId = message.message_id;
    const submittedData = completedForms[formMessageId];
    const { instructions, elements: formStructure } = parseFormElements(message);

    const [formData, setFormData] = useState({});
    const [formErrors, setFormErrors] = useState({});
    const [isSubmitting, setIsSubmitting] = useState(false);

    useEffect(() => {
        if (formStructure.length > 0 && submittedData === undefined) {
            const initialData = formStructure.reduce((acc, el) => {
                acc[el.name] = el.value || '';
                return acc;
            }, {});
            setFormData(initialData);
        }
    }, [formStructure, submittedData]);

    const handleInputChange = (event) => {
        const { name, value, type, checked } = event.target;
        setFormData(prev => ({
            ...prev,
            [name]: type === 'checkbox' ? checked : value,
        }));

        if (formErrors[name]) {
            setFormErrors(prev => {
                const newErrors = { ...prev };
                delete newErrors[name];
                return newErrors;
            });
        }
    };

    const validateForm = useCallback(() => {
        const errors = {};
        formStructure.forEach(element => {
            if (element.required && !formData[element.name]) {
                errors[element.name] = `${element.label || element.name} 是必填项`;
            }
        });
        setFormErrors(errors);
        return Object.keys(errors).length === 0;
    }, [formData, formStructure]);

    const handleSubmit = useRecoilCallback(({ set, snapshot }) => async (event) => {
        event.preventDefault();
        if (!validateForm() || isSubmitting) return;

        setIsSubmitting(true);
        const responseMessageId = uuidv4();
        const currentId = await snapshot.getPromise(currentConversationIdState);

        set(completedFormsState, (prev) => ({ ...prev, [formMessageId]: formData }));
        set(formResponsesState, (prev) => ({ ...prev, [responseMessageId]: formMessageId }));
        set(backgroundTasksState, (prev) => ({ ...prev, [responseMessageId]: "提交表单中..." }));

        const requestPayload = {
            id: responseMessageId,
            role: 'user',
            parts: [{ type: 'data', data: formData }],
            metadata: {
                conversation_id: currentId,
                message_id: responseMessageId,
            },
        };

        const stateSubmissionMessage = {
            message_id: responseMessageId,
            role: 'user',
            content: [[`提交了表单数据`, 'text/plain']],
            metadata: requestPayload.metadata,
        };
        set(messagesState, (prev) => [...prev, stateSubmissionMessage]);

        try {
            await api.sendMessage(requestPayload);
        } catch (error) {
            console.error("提交表单数据失败:", error);
            set(backgroundTasksState, (prev) => ({ ...prev, [responseMessageId]: "表单提交失败" }));
        } finally {
            setIsSubmitting(false);
        }
    }, [validateForm, isSubmitting, formData, formMessageId]);

    const handleCancel = useRecoilCallback(({ set, snapshot }) => async () => {
        setIsSubmitting(true);
        const cancelMessageId = uuidv4();
        const currentId = await snapshot.getPromise(currentConversationIdState);

        set(completedFormsState, (prev) => ({ ...prev, [formMessageId]: null }));
        set(formResponsesState, (prev) => ({ ...prev, [cancelMessageId]: formMessageId }));
        set(backgroundTasksState, (prev) => ({ ...prev, [cancelMessageId]: "取消表单中..." }));

        const requestPayload = {
            id: cancelMessageId,
            role: 'user',
            parts: [{ type: 'text', text: "rejected form entry" }],
            metadata: {
                conversation_id: currentId,
                message_id: cancelMessageId,
            },
        };

        const stateCancelMessage = {
            message_id: cancelMessageId,
            role: 'user',
            content: [['用户取消了表单', 'text/plain']],
            metadata: requestPayload.metadata,
        };
        set(messagesState, (prev) => [...prev, stateCancelMessage]);

        try {
            await api.sendMessage(requestPayload);
        } catch (error) {
            console.error("发送表单取消消息失败:", error);
            set(backgroundTasksState, (prev) => ({ ...prev, [cancelMessageId]: "取消表单失败" }));
        } finally {
            setIsSubmitting(false);
        }
    }, [formMessageId]);

    if (submittedData !== undefined) {
        const alignment = message.role === 'agent' ? 'flex-start' : 'flex-end';
        return (
            <Card sx={{ maxWidth: '75vw', my: 2, alignSelf: alignment }}>
                <CardContent>
                    <Typography variant="h6" gutterBottom>表单响应</Typography>
                    {submittedData ? (
                        <ReactMarkdown>
                            {Object.entries(submittedData)
                                .map(([key, value]) => `**${key}**: ${value}`)
                                .join('  \n')}
                        </ReactMarkdown>
                    ) : (
                        <Typography color="text.secondary" fontStyle="italic">
                            用户已取消表单。
                        </Typography>
                    )}
                </CardContent>
            </Card>
        );
    }

    if (!formStructure || formStructure.length === 0) {
        return <Alert severity="warning">无法解析表单结构。</Alert>;
    }

    const alignment = message.role === 'agent' ? 'flex-start' : 'flex-end';

    return (
        <Card sx={{ maxWidth: '75vw', my: 4, alignSelf: alignment }}>
            <CardContent>
                {instructions && (
                    <Typography variant="h6" gutterBottom>
                        {instructions}
                    </Typography>
                )}
                <form onSubmit={handleSubmit}>
                    <Stack spacing={2}>
                        {formStructure.map(element => (
                            <div key={element.name}>
                                <TextField
                                    id={element.name}
                                    name={element.name}
                                    label={`${element.label}${element.required ? ' *' : ''}`}
                                    type={element.formType}
                                    value={formData[element.name] || ''}
                                    onChange={handleInputChange}
                                    fullWidth
                                    required={element.required}
                                    error={!!formErrors[element.name]}
                                    helperText={formErrors[element.name]}
                                />
                            </div>
                        ))}
                        <Stack direction="row" justifyContent="flex-end" spacing={2} pt={2}>
                            <Button variant="outlined" onClick={handleCancel} disabled={isSubmitting}>
                                取消
                            </Button>
                            <Button type="submit" variant="contained" disabled={isSubmitting}>
                                {isSubmitting ? '提交中...' : '提交'}
                            </Button>
                        </Stack>
                    </Stack>
                </form>
            </CardContent>
        </Card>
    );
};

export default FormRenderer;
