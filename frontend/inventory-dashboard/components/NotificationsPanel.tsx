'use client';

import { useState, useEffect } from 'react';
import { getApiBaseUrl } from '../lib/apiBaseUrl';

interface PendingEmail {
  id: string;
  po_number: string;
  vendor_name: string;
  call_sid: string;
  call_duration: number;
  subject: string;
  body: string;
  pdf_url: string;
  created_at: string;
  status: 'pending' | 'sent' | 'failed';
  // Optional demo / regeneration helpers
  pdf_data_url?: string; // data:application/pdf;base64,...
  metadata?: {
    demo?: boolean;
    contact_person?: string;
    delivery_date?: string;
    total_amount?: number;
    items?: Array<{
      name: string;
      sku?: string;
      quantity: number;
      unit_price: number;
      category?: string;
      vendor?: string;
      lead_time_days?: number;
    }>;
    call_transcript?: string;
  };
  // Optional fields for richer notification semantics
  type?: 'vendor_call_success' | 'vendor_call_failure' | 'vendor_call_rejection';
  // Backend currently sends 'pending_email' (success), 'not_placed' (failure),
  // or 'rejected' (single vendor rejected, fallback in progress).
  order_status?: 'pending_email' | 'placed' | 'not_placed' | 'rejected';
  rejection_reason?: string;
  // Optional product name to help group related notifications
  product_name?: string;
}

export default function NotificationsPanel() {
  const [pendingEmails, setPendingEmails] = useState<PendingEmail[]>([]);
  const [selectedEmail, setSelectedEmail] = useState<PendingEmail | null>(null);
  const [sending, setSending] = useState(false);
  const [showSuccessModal, setShowSuccessModal] = useState(false);
  const [showPdfViewer, setShowPdfViewer] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string>('');
  const [showCallLogModal, setShowCallLogModal] = useState(false);
  const [callLog, setCallLog] = useState<{
    vendor_name: string;
    call_sid: string;
    timestamp: string;
    transcript: string;
    order_status: 'placed' | 'not_placed' | 'pending';
  } | null>(null);

  // Load notifications from localStorage (in production, fetch from API)
  useEffect(() => {
    const loadNotifications = () => {
      const stored = localStorage.getItem('pendingNotifications');
      if (stored) {
        try {
          const parsed = JSON.parse(stored);
          console.log('Loaded notifications from localStorage:', parsed);

          // Extract embedded rejected_vendors from success notifications
          // and create separate rejection notification entries
          let needsUpdate = false;
          const existingIds = new Set(parsed.map((n: any) => n.id));
          for (const item of [...parsed]) {
            if (item.rejected_vendors && Array.isArray(item.rejected_vendors)) {
              for (const rv of item.rejected_vendors) {
                const rejId = `notif-reject-${(rv.call_sid || '').slice(0, 8)}`;
                if (!existingIds.has(rejId)) {
                  parsed.push({
                    id: rejId,
                    type: 'vendor_call_rejection',
                    vendor_name: rv.vendor_name,
                    rejection_reason: rv.rejection_reason,
                    product_name: item.product_name || 'products',
                    po_number: 'N/A',
                    call_sid: rv.call_sid || '',
                    call_duration: 0,
                    subject: `Vendor Rejected: ${rv.vendor_name} - ${rv.rejection_reason}`,
                    body: `Vendor ${rv.vendor_name} was contacted but declined the order.\n\nRejection reason: ${rv.rejection_reason}`,
                    pdf_url: '',
                    created_at: item.created_at || new Date().toISOString(),
                    status: 'failed',
                    order_status: 'rejected',
                  });
                  existingIds.add(rejId);
                  needsUpdate = true;
                }
              }
              delete item.rejected_vendors;
              needsUpdate = true;
            }
          }
          if (needsUpdate) {
            localStorage.setItem('pendingNotifications', JSON.stringify(parsed));
          }

          // Validate and ensure proper typing
          const validated: PendingEmail[] = parsed.map((item: any) => {
            console.log('Notification PDF URL:', item.po_number, '→', item.pdf_url);
            return {
              ...item,
              status: (item.status === 'sent' || item.status === 'failed' ? item.status : 'pending') as 'pending' | 'sent' | 'failed'
            };
          });

          // De-duplicate notifications so we don't show both an early
          // "ORDER NOT PLACED" and a later "ORDER PLACED" for the same
          // vendor/product. Newest notification wins.
          const sorted = [...validated].sort((a, b) => {
            const aTime = a.created_at || '';
            const bTime = b.created_at || '';
            return bTime.localeCompare(aTime);
          });

          const seen = new Set<string>();
          const deduped: PendingEmail[] = [];

          for (const notif of sorted) {
            // Include type in dedup key so rejection + success for same vendor are both shown
            const key = `${notif.vendor_name || ''}::${notif.product_name || ''}::${notif.type || notif.status || ''}`;
            if (!seen.has(key)) {
              seen.add(key);
              deduped.push(notif);
            }
          }

          setPendingEmails(deduped);
        } catch (error) {
          console.error('Error loading notifications:', error);
        }
      }
    };
    
    loadNotifications();
    
    // Poll for updates every 3 seconds
    const interval = setInterval(loadNotifications, 3000);
    
    return () => clearInterval(interval);
  }, []);

  const handleSendEmail = async (email: PendingEmail) => {
    setSending(true);
    
    try {
      // In production, call API to send email
      await new Promise(resolve => setTimeout(resolve, 2000));

      // Notify backend that this order's email has been sent so it can be
      // treated as a fully successful order in the Orders panel.
      try {
        const apiUrl = getApiBaseUrl();
        await fetch(`${apiUrl}/api/orders/mark-sent`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ po_number: email.po_number }),
        });
      } catch (err) {
        console.error('Error marking order as sent in backend:', err);
      }
      
      // Update status
      const updatedEmails = pendingEmails.map(e => 
        e.id === email.id ? { ...e, status: 'sent' as const } : e
      );
      setPendingEmails(updatedEmails);
      localStorage.setItem('pendingNotifications', JSON.stringify(updatedEmails));
      
      setSelectedEmail(null);
      setShowSuccessModal(true);
      
      // Auto-hide success modal after 3 seconds
      setTimeout(() => setShowSuccessModal(false), 3000);
    } catch (error) {
      alert('❌ Failed to send email');
    } finally {
      setSending(false);
    }
  };

  const handleViewCallLog = async (email: PendingEmail) => {
    const apiUrl = getApiBaseUrl();
    let transcript = '';
    let callStatus: string | null = null;

    // For failure notifications (order not placed), we already store the
    // final transcript directly on the notification metadata. Prefer that
    // first so the UI can always show something even if the backend store
    // is slightly behind or unavailable.
    const anyEmail: any = email;
    if (anyEmail?.metadata?.call_transcript) {
      transcript = anyEmail.metadata.call_transcript;
    }

    // Try backend transcript first if we have a call SID
    if (email.call_sid && !transcript) {
      try {
        const resp = await fetch(`${apiUrl}/api/get-transcript/${email.call_sid}`);
        const data = await resp.json();
        if (data.success && data.transcript) {
          transcript = data.transcript;
        } else {
          // Capture backend message if available (e.g. "Transcript not available yet")
          if (!transcript && data.message) {
            transcript = data.message;
          }
        }
      } catch (err) {
        console.error('Error fetching transcript from backend:', err);
      }

      // Also try to fetch call status so we can explain why a transcript is missing
      try {
        const statusResp = await fetch(`${apiUrl}/api/get-call-status/${email.call_sid}`);
        const statusData = await statusResp.json();
        if (statusData && statusData.status) {
          callStatus = statusData.status as string;
        }
      } catch (err) {
        console.error('Error fetching call status from backend:', err);
      }
    }

    // If we still don't have a transcript, provide a clearer explanation
    if (!transcript) {
      if (callStatus && ['no-answer', 'failed', 'busy', 'canceled'].includes(callStatus.toLowerCase())) {
        transcript = `Call did not connect (status: ${callStatus}). No transcript was recorded.`;
      } else if (callStatus && callStatus.toLowerCase() !== 'completed') {
        transcript = `Call status is currently "${callStatus}". Transcript will be available once the call fully completes.`;
      } else {
        transcript = 'Transcript not available yet.';
      }
    }

    // Derive a human-meaningful order status for the call log:
    // - 'not_placed'  → vendor declined / failure notification
    // - 'placed'      → email has been sent
    // - 'pending'     → call completed, draft ready, email not yet sent
    let order_status: 'placed' | 'not_placed' | 'pending' = 'pending';
    if (email.type === 'vendor_call_rejection' || email.order_status === 'rejected') {
      order_status = 'not_placed';
    } else if (email.status === 'failed' || email.order_status === 'not_placed') {
      order_status = 'not_placed';
    } else if (email.status === 'sent' || email.order_status === 'placed') {
      order_status = 'placed';
    } else {
      order_status = 'pending';
    }

    setCallLog({
      vendor_name: email.vendor_name,
      call_sid: email.call_sid,
      timestamp: email.created_at,
      transcript,
      order_status,
    });
    setShowCallLogModal(true);
  };

  const handleDeleteEmail = (emailId: string) => {
    if (confirm('Delete this draft?')) {
      const updatedEmails = pendingEmails.filter(e => e.id !== emailId);
      setPendingEmails(updatedEmails);
      localStorage.setItem('pendingNotifications', JSON.stringify(updatedEmails));
    }
  };

  return (
    <div style={{
      padding: '32px',
      background: 'linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%)',
      minHeight: '100%'
    }}>
      {/* Header */}
      <div style={{ marginBottom: '32px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '12px' }}>
          <div style={{
            width: '56px',
            height: '56px',
            background: 'linear-gradient(135deg, #3B82F6 0%, #2563EB 100%)',
            borderRadius: '16px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '28px',
            boxShadow: '0 4px 12px rgba(59, 130, 246, 0.3)'
          }}>
            📧
          </div>
          <div style={{ flex: 1 }}>
            <h1 style={{
              fontSize: '32px',
              fontWeight: '700',
              margin: 0,
              background: 'linear-gradient(135deg, #3B82F6 0%, #2563EB 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent'
            }}>
              Notifications
            </h1>
            <p style={{ fontSize: '14px', color: '#6B7280', margin: 0 }}>
              Pending emails and call follow-ups
            </p>
          </div>
          {pendingEmails.length > 0 && (
            <button
              onClick={() => {
                if (confirm('Clear all notifications? This cannot be undone.')) {
                  localStorage.removeItem('pendingNotifications');
                  setPendingEmails([]);
                }
              }}
              style={{
                padding: '10px 20px',
                background: '#FEE2E2',
                color: '#DC2626',
                border: '1px solid #DC2626',
                borderRadius: '8px',
                fontSize: '14px',
                fontWeight: '600',
                cursor: 'pointer',
                transition: 'all 0.2s'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = '#DC2626';
                e.currentTarget.style.color = 'white';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = '#FEE2E2';
                e.currentTarget.style.color = '#DC2626';
              }}
            >
              🗑️ Clear All
            </button>
          )}
        </div>
      </div>

      {/* Stats */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: '20px',
        marginBottom: '32px'
      }}>
        <div style={{
          background: 'white',
          padding: '24px',
          borderRadius: '16px',
          boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
          border: '1px solid #E5E7EB'
        }}>
          <div style={{ fontSize: '13px', color: '#6B7280', marginBottom: '8px', fontWeight: '600' }}>
            PENDING EMAILS
          </div>
          <div style={{ fontSize: '36px', fontWeight: '800', color: '#F59E0B' }}>
            {pendingEmails.filter(e => e.status === 'pending').length}
          </div>
        </div>

        <div style={{
          background: 'white',
          padding: '24px',
          borderRadius: '16px',
          boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
          border: '1px solid #E5E7EB'
        }}>
          <div style={{ fontSize: '13px', color: '#6B7280', marginBottom: '8px', fontWeight: '600' }}>
            SENT TODAY
          </div>
          <div style={{ fontSize: '36px', fontWeight: '800', color: '#10B981' }}>
            {pendingEmails.filter(e => e.status === 'sent').length}
          </div>
        </div>

        <div style={{
          background: 'white',
          padding: '24px',
          borderRadius: '16px',
          boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
          border: '1px solid #E5E7EB'
        }}>
          <div style={{ fontSize: '13px', color: '#6B7280', marginBottom: '8px', fontWeight: '600' }}>
            TOTAL CALLS
          </div>
          <div style={{ fontSize: '36px', fontWeight: '800', color: '#3B82F6' }}>
            {pendingEmails.length}
          </div>
        </div>
      </div>

      {/* Pending Emails List */}
      {pendingEmails.length === 0 ? (
        <div style={{
          background: 'white',
          borderRadius: '16px',
          padding: '60px 40px',
          textAlign: 'center',
          boxShadow: '0 4px 12px rgba(0,0,0,0.08)'
        }}>
          <div style={{ fontSize: '64px', marginBottom: '16px' }}>📭</div>
          <h3 style={{ fontSize: '20px', fontWeight: '600', marginBottom: '8px', color: '#374151' }}>
            No Pending Notifications
          </h3>
          <p style={{ fontSize: '14px', color: '#6B7280' }}>
            When you make vendor calls, email drafts will appear here for review and sending.
          </p>
        </div>
      ) : (
        <div style={{
          background: 'white',
          borderRadius: '16px',
          boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
          overflow: 'hidden'
        }}>
          {pendingEmails.map((email) => (
            <div
              key={email.id}
              style={{
                padding: '24px',
                borderBottom: '1px solid #E5E7EB',
                cursor: 'pointer',
                transition: 'background 0.2s'
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = '#F9FAFB')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'white')}
              onClick={() => {
                // For failures and rejections, clicking the card should show the call log,
                // not an email preview (since no PO/email were generated).
                if (email.status === 'failed' || email.type === 'vendor_call_rejection') {
                  handleViewCallLog(email);
                } else {
                  setSelectedEmail(email);
                }
              }}
            >
              <div style={{ display: 'flex', alignItems: 'start', gap: '16px' }}>
                <div style={{
                  width: '48px',
                  height: '48px',
                  background:
                    email.type === 'vendor_call_rejection'
                      ? 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)'
                      : email.status === 'failed'
                      ? 'linear-gradient(135deg, #EF4444 0%, #DC2626 100%)'
                      : email.status === 'pending'
                      ? 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)'
                      : 'linear-gradient(135deg, #10B981 0%, #059669 100%)',
                  borderRadius: '12px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '24px',
                  flexShrink: 0
                }}>
                  {email.type === 'vendor_call_rejection' ? '🚫' : email.status === 'failed' ? '❌' : email.status === 'pending' ? '📧' : '✅'}
                </div>

                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                    <h3 style={{ fontSize: '16px', fontWeight: '600', margin: 0 }}>
                      {email.vendor_name}
                    </h3>
                    <span
                      style={{
                        padding: '4px 12px',
                        background:
                          email.type === 'vendor_call_rejection'
                            ? '#FEF3C7'
                            : email.status === 'failed'
                            ? '#FEE2E2'
                            : email.status === 'pending'
                            ? '#FEF3C7'
                            : '#D1FAE5',
                        color:
                          email.type === 'vendor_call_rejection'
                            ? '#92400E'
                            : email.status === 'failed'
                            ? '#B91C1C'
                            : email.status === 'pending'
                            ? '#92400E'
                            : '#065F46',
                        borderRadius: '6px',
                        fontSize: '11px',
                        fontWeight: '600',
                      }}
                    >
                      {email.type === 'vendor_call_rejection'
                        ? `VENDOR REJECTED${email.rejection_reason ? ' - ' + email.rejection_reason : ''}`
                        : email.status === 'failed'
                        ? 'ORDER NOT PLACED'
                        : email.status === 'pending'
                        ? 'CALL COMPLETED - EMAIL PENDING'
                        : 'EMAIL SENT'}
                    </span>
                    {/* Only mark ORDER PLACED once email is actually sent */}
                    {email.status === 'sent' && (
                      <span
                        style={{
                          padding: '4px 10px',
                          background: '#ECFDF3',
                          color: '#166534',
                          borderRadius: '999px',
                          fontSize: '10px',
                          fontWeight: '700',
                        }}
                      >
                        ORDER PLACED
                      </span>
                    )}
                  </div>

                  <p style={{ fontSize: '14px', color: '#374151', margin: '0 0 8px 0' }}>
                    {email.subject}
                  </p>

                  <div style={{ display: 'flex', gap: '16px', fontSize: '12px', color: '#6B7280' }}>
                    {email.call_duration !== undefined && (
                      <span>📞 Call: {email.call_duration || 0}s</span>
                    )}
                    {email.po_number && email.po_number !== 'N/A' && (
                      <span>📄 PO: {email.po_number}</span>
                    )}
                    {email.status !== 'failed' && (
                      <span>📎 PDF attached</span>
                    )}
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '8px' }}>
                  {email.status === 'pending' && email.type !== 'vendor_call_rejection' && (
                    <>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleSendEmail(email);
                        }}
                        disabled={sending}
                        style={{
                          padding: '8px 16px',
                          background: 'linear-gradient(135deg, #3B82F6 0%, #2563EB 100%)',
                          color: 'white',
                          border: 'none',
                          borderRadius: '8px',
                          fontSize: '13px',
                          fontWeight: '600',
                          cursor: sending ? 'not-allowed' : 'pointer',
                          opacity: sending ? 0.5 : 1
                        }}
                      >
                        {sending ? 'Sending...' : 'Send'}
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteEmail(email.id);
                        }}
                        style={{
                          padding: '8px 16px',
                          background: '#FEE2E2',
                          color: '#DC2626',
                          border: 'none',
                          borderRadius: '8px',
                          fontSize: '13px',
                          fontWeight: '600',
                          cursor: 'pointer'
                        }}
                      >
                        Delete
                      </button>
                    </>
                  )}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleViewCallLog(email);
                    }}
                    style={{
                      padding: '8px 16px',
                      background: '#F3F4F6',
                      color: '#111827',
                      border: 'none',
                      borderRadius: '8px',
                      fontSize: '13px',
                      fontWeight: '600',
                      cursor: 'pointer'
                    }}
                  >
                    📞 View Call Log
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Email Preview Modal */}
      {selectedEmail && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 9999,
          padding: '20px'
        }} onClick={() => setSelectedEmail(null)}>
          <div style={{
            background: 'white',
            borderRadius: '16px',
            maxWidth: '700px',
            width: '100%',
            maxHeight: '90vh',
            overflow: 'auto',
            boxShadow: '0 20px 60px rgba(0,0,0,0.3)'
          }} onClick={(e) => e.stopPropagation()}>
            
            <div style={{ padding: '24px', borderBottom: '1px solid #E5E7EB' }}>
              <h2 style={{ fontSize: '20px', fontWeight: '700', margin: '0 0 8px 0' }}>
                Email Preview
              </h2>
              <p style={{ fontSize: '14px', color: '#6B7280', margin: 0 }}>
                {selectedEmail.vendor_name} • PO #{selectedEmail.po_number}
              </p>
            </div>

            <div style={{ padding: '24px' }}>
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '600', marginBottom: '8px' }}>
                  Subject
                </label>
                <input
                  type="text"
                  value={selectedEmail.subject}
                  readOnly
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    border: '1px solid #E5E7EB',
                    borderRadius: '8px',
                    fontSize: '14px'
                  }}
                />
              </div>

              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '600', marginBottom: '8px' }}>
                  Email Body
                </label>
                <textarea
                  value={selectedEmail.body}
                  readOnly
                  rows={12}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    border: '1px solid #E5E7EB',
                    borderRadius: '8px',
                    fontSize: '13px',
                    fontFamily: 'monospace',
                    resize: 'vertical'
                  }}
                />
              </div>

              <div style={{
                background: '#F9FAFB',
                padding: '12px',
                borderRadius: '8px',
                marginBottom: '20px'
              }}>
                <div style={{ fontSize: '13px', fontWeight: '600', marginBottom: '8px' }}>
                  Attachments:
                </div>
                {selectedEmail.pdf_url && selectedEmail.pdf_url !== '#' ? (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      console.log('Opening PDF:', selectedEmail.pdf_url);
                      setPdfUrl(selectedEmail.pdf_url);
                      setShowPdfViewer(true);
                    }}
                    style={{
                      width: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '12px',
                      background: 'white',
                      border: '2px solid #3B82F6',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      transition: 'all 0.2s'
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = '#EFF6FF';
                      e.currentTarget.style.transform = 'translateY(-2px)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = 'white';
                      e.currentTarget.style.transform = 'translateY(0)';
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontSize: '20px' }}>📎</span>
                      <span style={{ fontSize: '14px', fontWeight: '600', color: '#1F2937' }}>
                        {selectedEmail.po_number}.pdf
                      </span>
                    </div>
                    <div style={{
                      padding: '6px 12px',
                      background: '#3B82F6',
                      color: 'white',
                      borderRadius: '6px',
                      fontSize: '12px',
                      fontWeight: '600'
                    }}>
                      📄 View PDF
                    </div>
                  </button>
                ) : (
                  <button
                    onClick={async (e) => {
                      e.stopPropagation();
                      const API_BASE_URL = getApiBaseUrl();
                      try {
                        const btn = e.currentTarget;
                        btn.textContent = 'Generating PDF...';
                        const resp = await fetch(`${API_BASE_URL}/api/generate-po-pdf`, {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({
                            po_number: selectedEmail.po_number,
                            vendor_name: selectedEmail.vendor_name,
                            metadata: selectedEmail.metadata || {},
                          }),
                        });
                        const data = await resp.json();
                        if (data.success && data.pdf_url) {
                          // Update notification in state and localStorage
                          const updated = pendingEmails.map(em =>
                            em.id === selectedEmail.id ? { ...em, pdf_url: data.pdf_url } : em
                          );
                          setPendingEmails(updated);
                          localStorage.setItem('pendingNotifications', JSON.stringify(updated));
                          setSelectedEmail({ ...selectedEmail, pdf_url: data.pdf_url });
                          setPdfUrl(data.pdf_url);
                          setShowPdfViewer(true);
                        } else {
                          alert('Could not generate PDF: ' + (data.error || 'Unknown error'));
                        }
                      } catch (err) {
                        console.error('PDF generation error:', err);
                        alert('Failed to generate PDF');
                      }
                    }}
                    style={{
                      width: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '12px',
                      background: '#FFF7ED',
                      border: '2px solid #F59E0B',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      transition: 'all 0.2s'
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = '#FEF3C7';
                      e.currentTarget.style.transform = 'translateY(-2px)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = '#FFF7ED';
                      e.currentTarget.style.transform = 'translateY(0)';
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontSize: '20px' }}>📎</span>
                      <span style={{ fontSize: '14px', fontWeight: '600', color: '#1F2937' }}>
                        {selectedEmail.po_number}.pdf
                      </span>
                    </div>
                    <div style={{
                      padding: '6px 12px',
                      background: '#F59E0B',
                      color: 'white',
                      borderRadius: '6px',
                      fontSize: '12px',
                      fontWeight: '600'
                    }}>
                      Generate PDF
                    </div>
                  </button>
                )}
              </div>

              <div style={{ display: 'flex', gap: '12px' }}>
                <button
                  onClick={() => handleSendEmail(selectedEmail)}
                  disabled={sending || selectedEmail.status === 'sent'}
                  style={{
                    flex: 1,
                    padding: '12px',
                    background: selectedEmail.status === 'sent' ? '#10B981' : 'linear-gradient(135deg, #3B82F6 0%, #2563EB 100%)',
                    color: 'white',
                    border: 'none',
                    borderRadius: '12px',
                    fontSize: '16px',
                    fontWeight: '600',
                    cursor: selectedEmail.status === 'sent' ? 'not-allowed' : 'pointer',
                    opacity: sending ? 0.5 : 1
                  }}
                >
                  {selectedEmail.status === 'sent' ? '✅ Sent' : sending ? 'Sending...' : '📧 Send Email'}
                </button>
                <button
                  onClick={() => setSelectedEmail(null)}
                  style={{
                    padding: '12px 24px',
                    background: '#E5E7EB',
                    color: '#374151',
                    border: 'none',
                    borderRadius: '12px',
                    fontSize: '16px',
                    fontWeight: '600',
                    cursor: 'pointer'
                  }}
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Success Modal */}
      {showSuccessModal && (
        <div style={{
          position: 'fixed',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          background: 'white',
          borderRadius: '20px',
          padding: '40px',
          boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
          zIndex: 10000,
          textAlign: 'center',
          minWidth: '400px',
          animation: 'slideIn 0.3s ease-out'
        }}>
          <div style={{
            width: '80px',
            height: '80px',
            background: 'linear-gradient(135deg, #10B981 0%, #059669 100%)',
            borderRadius: '50%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            margin: '0 auto 24px',
            fontSize: '40px',
            boxShadow: '0 8px 24px rgba(16, 185, 129, 0.3)'
          }}>
            ✓
          </div>
          <h2 style={{
            fontSize: '28px',
            fontWeight: '700',
            margin: '0 0 12px 0',
            color: '#059669'
          }}>
            Email Sent Successfully!
          </h2>
          <p style={{
            fontSize: '16px',
            color: '#6B7280',
            margin: 0
          }}>
            Your purchase order has been sent to the vendor
          </p>
        </div>
      )}

      {/* Backdrop for success modal */}
      {showSuccessModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.4)',
          zIndex: 9999
        }} onClick={() => setShowSuccessModal(false)} />
      )}

      {/* PDF Viewer Modal */}
      {showPdfViewer && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.8)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 10001,
          padding: '20px'
        }} onClick={() => setShowPdfViewer(false)}>
          <div style={{
            background: 'white',
            borderRadius: '16px',
            width: '90%',
            height: '90%',
            maxWidth: '1200px',
            display: 'flex',
            flexDirection: 'column',
            boxShadow: '0 20px 60px rgba(0,0,0,0.5)'
          }} onClick={(e) => e.stopPropagation()}>
            
            {/* Header */}
            <div style={{
              padding: '20px',
              borderBottom: '1px solid #E5E7EB',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between'
            }}>
              <h2 style={{ fontSize: '20px', fontWeight: '700', margin: 0 }}>
                📄 Purchase Order
              </h2>
              <div style={{ display: 'flex', gap: '12px' }}>
                <button
                  onClick={() => window.open(pdfUrl, '_blank')}
                  style={{
                    padding: '8px 16px',
                    background: '#3B82F6',
                    color: 'white',
                    border: 'none',
                    borderRadius: '8px',
                    fontSize: '14px',
                    fontWeight: '600',
                    cursor: 'pointer'
                  }}
                >
                  🔗 Open in New Tab
                </button>
                <button
                  onClick={() => setShowPdfViewer(false)}
                  style={{
                    padding: '8px 16px',
                    background: '#E5E7EB',
                    color: '#374151',
                    border: 'none',
                    borderRadius: '8px',
                    fontSize: '14px',
                    fontWeight: '600',
                    cursor: 'pointer'
                  }}
                >
                  ✕ Close
                </button>
              </div>
            </div>

            {/* PDF Viewer */}
            <div style={{ flex: 1, overflow: 'hidden' }}>
              <iframe
                src={pdfUrl}
                style={{
                  width: '100%',
                  height: '100%',
                  border: 'none'
                }}
                title="Purchase Order"
              />
            </div>
          </div>
        </div>
      )}

      {/* Call Log / Transcript Modal */}
      {showCallLogModal && callLog && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 9999,
          padding: '20px'
        }} onClick={() => setShowCallLogModal(false)}>
          <div style={{
            background: 'white',
            borderRadius: '16px',
            maxWidth: '800px',
            width: '100%',
            maxHeight: '90vh',
            overflow: 'auto',
            boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
            padding: '24px'
          }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px' }}>
              <div>
                <h2 style={{ fontSize: '20px', fontWeight: '700', margin: 0 }}>
                  Call Log • {callLog.vendor_name}
                </h2>
                <p style={{ fontSize: '13px', color: '#6B7280', margin: '4px 0 0 0' }}>
                  {new Date(callLog.timestamp).toLocaleString()} •{' '}
                  {callLog.order_status === 'not_placed'
                    ? 'Vendor rejected the order – no PO or email was generated. System is trying the next vendor.'
                    : callLog.order_status === 'pending'
                    ? 'Call completed – PO drafted, email not sent yet.'
                    : 'Order placed – PO generated and email sent.'}
                </p>
              </div>
              <button
                onClick={() => setShowCallLogModal(false)}
                style={{
                  padding: '8px 12px',
                  background: '#E5E7EB',
                  border: 'none',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  fontSize: '13px',
                  fontWeight: '600'
                }}
              >
                ✕ Close
              </button>
            </div>
            <div style={{
              background: '#F9FAFB',
              borderRadius: '12px',
              padding: '16px',
              fontSize: '14px',
              color: '#374151',
              whiteSpace: 'pre-wrap'
            }}>
              {callLog.transcript || 'Transcript not available yet.'}
            </div>
          </div>
        </div>
      )}

      <style jsx>{`
        @keyframes slideIn {
          from {
            opacity: 0;
            transform: translate(-50%, -60%);
          }
          to {
            opacity: 1;
            transform: translate(-50%, -50%);
          }
        }
      `}</style>
    </div>
  );
}
