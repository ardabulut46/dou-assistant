<script lang="ts">
	import { browser } from '$app/environment';
	import { afterNavigate } from '$app/navigation';
	import { page } from '$app/stores';
	import ObsShell from '$lib/components/obs/ObsShell.svelte';
	import { user } from '$lib/stores';
	import {
		getDouStudentAdvisor,
		getDouStudentProfile,
		getDouStudentEnrollments,
		getDouStudentGrades,
		getDouStudentGpaSummary,
		getDouStudentTranscript,
		getDouStudentAttendance,
		getDouStudentExams,
		getDouStudentSchedule,
		getDouAnnouncements,
		getDouInbox,
		getDouSent,
		getDouStudentDocumentRequests,
		createDouDocumentRequest,
		getDouTerms,
		getDouGraduationStatus,
		getDouFinancialInfo,
		getDouCurriculumStatus,
		getDouTodoList,
		getDouApplications,
		createDouApplication,
		getDouPrepSchedule,
		getDouPrepExams,
		getDouPrepGrades,
		getDouPrepAttendance,
		getDouInternships,
		createDouInternship,
		getDouCreditTransfers,
		createDouCreditTransfer,
		type DouAdvisorResponse,
		type DouTerm,
		type DouStudentProfile,
		type DouEnrollment,
		type DouGradeEntry,
		type DouAttendanceRow,
		type DouExam,
		type DouScheduleRow,
		type DouAnnouncement,
		type DouMessage,
		type DouDocumentRequest,
		type DouGraduationStatus,
		type DouFinancialInfo,
		type DouCurriculumStatus,
		type DouTodoItem,
		type DouApplication,
		type DouInternship,
		type DouCreditTransfer,
		type DouPrepScheduleRow,
		type DouPrepExam,
		type DouPrepGrade,
		type DouPrepAttendanceRow,
	} from '$lib/apis/douAcademic';

	// ---------------------------------------------------------------------------
	// Sayfa meta haritası
	// ---------------------------------------------------------------------------
	const labels: Record<string, { title: string; hint: string; api?: string }> = {
		'/obs/genel/kullanim-kilavuzu':      { title: 'Kullanım Kılavuzu',              hint: 'Sistem kullanım rehberi.' },
		'/obs/genel/ozluk-bilgileri':        { title: 'Özlük Bilgileri',               hint: 'GET /api/v1/student/me/profile',         api: 'profile' },
		'/obs/genel/genel-bilgiler':         { title: 'Genel Bilgiler',                hint: 'GET /api/v1/student/me/profile',         api: 'profile' },
		'/obs/genel/akademik-takvim':        { title: 'Akademik Takvim',               hint: 'GET /api/v1/terms',                     api: 'terms' },
		'/obs/genel/danisman-bilgileri':     { title: 'Danışman Bilgileri',            hint: 'GET /api/v1/student/me/advisor',        api: 'advisor' },
		'/obs/genel/alinan-dersler':         { title: 'Alınan Dersler',               hint: 'GET /api/v1/student/me/enrollments',    api: 'enrollments' },
		'/obs/genel/acilan-bolum-dersleri':  { title: 'Açılan Bölüm Dersleri',        hint: 'GET /api/v1/departments (mock)' },
		'/obs/genel/sinav-takvimi':          { title: 'Sınav Takvimi',                hint: 'GET /api/v1/student/me/exams',          api: 'exams' },
		'/obs/genel/ders-programi':          { title: 'Ders Programı',                hint: 'GET /api/v1/student/me/schedule',       api: 'schedule' },
		'/obs/genel/harc-bilgileri':         { title: 'Harç Bilgileri',               hint: 'GET /api/v1/student/me/financial',         api: 'financial' },
		'/obs/genel/staj-bilgileri':         { title: 'Staj Bilgileri',               hint: 'GET /api/v1/student/me/internship',        api: 'internship' },
		'/obs/genel/genel-duyurular':        { title: 'Genel Duyurular',              hint: 'GET /api/v1/announcements',                api: 'announcements' },
		'/obs/genel/mezuniyet-onay-bilgileri':{ title: 'Mezuniyet Onay Bilgileri',    hint: 'GET /api/v1/student/me/graduation-status', api: 'graduation' },

		'/obs/ders-donem/ders-kayit':        { title: 'Ders Kayıt',                   hint: 'POST /api/v1/student/me/applications',     api: 'application-form', appType: 'ders_kayit' },
		'/obs/ders-donem/ders-ekle-birak':   { title: 'Ders Ekle/Bırak',             hint: 'GET /api/v1/student/me/enrollments',       api: 'enrollments' },
		'/obs/ders-donem/donem-ortalamalari':{ title: 'Dönem Ortalamaları',           hint: 'GET /api/v1/student/me/gpa-summary',       api: 'gpa' },
		'/obs/ders-donem/not-listesi':       { title: 'Not Listesi',                  hint: 'GET /api/v1/student/me/grades',            api: 'grades' },
		'/obs/ders-donem/transkript':        { title: 'Transkript',                   hint: 'GET /api/v1/student/me/transcript',        api: 'transcript' },
		'/obs/ders-donem/transkript-senaryosu': { title: 'Transkript Senaryosu',      hint: 'GET /api/v1/student/me/transcript',        api: 'transcript' },
		'/obs/ders-donem/diger-belgeler':    { title: 'Diğer Belgeler',              hint: 'POST /api/v1/student/me/document-requests', api: 'doc-request' },
		'/obs/ders-donem/mufredat-durum':    { title: 'Müfredat Durum',              hint: 'GET /api/v1/student/me/curriculum-status', api: 'curriculum' },
		'/obs/ders-donem/mufredat-bilgi-paketi': { title: 'Müfredat Bilgi Paketi',   hint: 'GET /api/v1/student/me/curriculum-status', api: 'curriculum' },
		'/obs/ders-donem/staj-basvurusu':    { title: 'Staj Başvurusu',              hint: 'POST /api/v1/student/me/internship',       api: 'internship' },
		'/obs/ders-donem/devamsizlik-durumu':{ title: 'Devamsızlık Durumu',          hint: 'GET /api/v1/student/me/attendance',        api: 'attendance' },

		'/obs/form/anketler':                { title: 'Anketler',                     hint: 'GET /api/v1/student/me/applications?application_type=anket', api: 'applications', appType: 'anket' },
		'/obs/form/degerlendirme-formlari':  { title: 'Değerlendirme Formları',       hint: 'GET /api/v1/student/me/applications?application_type=degerlendirme', api: 'applications', appType: 'degerlendirme' },
		'/obs/form/hazirlik-deger-formlari': { title: 'Hazırlık Değerlendirme Formları', hint: 'GET /api/v1/student/me/applications?application_type=hazirlik_deger', api: 'applications', appType: 'hazirlik_deger' },
		'/obs/form/ogrenci-bilgi-formu':     { title: 'Öğrenci Bilgi Formu',          hint: 'GET /api/v1/student/me/profile',          api: 'profile' },

		'/obs/hazirlik/sinav-takvimi':       { title: 'Hazırlık Sınav Takvimi',       hint: 'GET /api/v1/student/me/prep/exams',       api: 'prep-exams' },
		'/obs/hazirlik/not-listesi':         { title: 'Hazırlık Not Listesi',          hint: 'GET /api/v1/student/me/prep/grades',      api: 'prep-grades' },
		'/obs/hazirlik/devamsizlik-durumu':  { title: 'Hazırlık Devamsızlık',         hint: 'GET /api/v1/student/me/prep/attendance',  api: 'prep-attendance' },
		'/obs/hazirlik/hazirlik-ders-programi': { title: 'Hazırlık Ders Programı',   hint: 'GET /api/v1/student/me/prep/schedule',    api: 'prep-schedule' },

		'/obs/basvuru/degisim-prog-basvuru-islemleri-v2': { title: 'Değişim Programı Başvurusu', hint: 'POST /api/v1/student/me/applications', api: 'application-form', appType: 'degisim_programi' },
		'/obs/basvuru/tek-ders-basvuru':     { title: 'Tek Ders Başvuru',             hint: 'POST /api/v1/student/me/applications', api: 'application-form', appType: 'tek_ders' },
		'/obs/basvuru/ek-sinav-basvuru':     { title: 'Ek Sınav Başvuru',             hint: 'POST /api/v1/student/me/applications', api: 'application-form', appType: 'ek_sinav' },
		'/obs/basvuru/cap-basvuru':          { title: 'ÇAP Başvuru',                  hint: 'POST /api/v1/student/me/applications', api: 'application-form', appType: 'cap' },
		'/obs/basvuru/yandal-basvuru':       { title: 'Yandal Başvuru',               hint: 'POST /api/v1/student/me/applications', api: 'application-form', appType: 'yandal' },
		'/obs/basvuru/kayit-dondurma-basvuru': { title: 'Kayıt Dondurma Başvuru',    hint: 'POST /api/v1/student/me/applications', api: 'application-form', appType: 'kayit_dondurma' },
		'/obs/basvuru/mazeret-sinavi-basvuru': { title: 'Mazeret Sınavı Başvuru',    hint: 'POST /api/v1/student/me/applications', api: 'application-form', appType: 'mazeret_sinav' },
		'/obs/basvuru/ek-sinav-basvuru-v2':  { title: 'Ek Sınav Başvuru (V2)',        hint: 'POST /api/v1/student/me/applications', api: 'application-form', appType: 'ek_sinav_v2' },
		'/obs/basvuru/ek-sinav-basvuru-islemleri': { title: 'Ek Sınav Başvuru İşlemleri', hint: 'GET /api/v1/student/me/applications', api: 'applications', appType: 'ek_sinav' },
		'/obs/basvuru/tek-ders-basvuru-islemleri': { title: 'Tek Ders Başvuru İşlemleri', hint: 'GET /api/v1/student/me/applications', api: 'applications', appType: 'tek_ders' },

		'/obs/staj/ogrenci-staj-islemleri':  { title: 'Öğrenci Staj İşlemleri',       hint: 'GET /api/v1/student/me/internship',       api: 'internship' },
		'/obs/intibak/intibak-basvuru':      { title: 'İntibak Başvuru',              hint: 'POST /api/v1/student/me/credit-transfer', api: 'credit-transfer' },

		'/obs/kullanici/yapilacaklar-listesi': { title: 'Yapılacaklar Listesi',       hint: 'GET /api/v1/student/me/todo-list',         api: 'todo' },
		'/obs/kullanici/gelen-mesajlar':     { title: 'Gelen Mesajlar',               hint: 'GET /api/v1/messages/inbox',               api: 'inbox' },
		'/obs/kullanici/gonderilen-mesajlar':{ title: 'Gönderilen Mesajlar',          hint: 'GET /api/v1/messages/sent',                api: 'sent' },
		'/obs/kullanici/belge-talebi':       { title: 'Belge Talebi',                 hint: 'POST /api/v1/student/me/document-requests', api: 'doc-request' },
		'/obs/kullanici/sifre-degistir':     { title: 'Şifre Değiştir',              hint: 'PUT /api/v1/auth/change-password',          api: 'change-password' },
		'/obs/kullanici/fotograf-guncelle':  { title: 'Fotoğraf Güncelle',            hint: 'PUT /api/v1/user/profile/photo',            api: 'photo-update' },
	};

	$: rest = $page.params.path || '';
	$: activePath = `/obs/${rest}`;

	const prettify = (s: string) =>
		decodeURIComponent(s)
			.split('/')
			.filter(Boolean)
			.at(-1)
			?.replaceAll('-', ' ')
			?.replace(/\b\w/g, (c) => c.toUpperCase()) ?? 'OBS';

	$: meta      = labels[activePath] ?? { title: rest ? prettify(rest) : 'OBS', hint: 'Demo içerik.' };
	$: pageTitle = meta.title;
	$: hint      = meta.hint;
	$: apiKey    = (meta as { api?: string }).api ?? '';
	$: appType   = (meta as { appType?: string }).appType ?? '';

	// ---------------------------------------------------------------------------
	// Mock API yükleme durumu
	// ---------------------------------------------------------------------------
	let loading = false;
	let loadErr: string | null = null;

	// Veri alanları
	let profile:       DouStudentProfile | null  = null;
	let terms:         DouTerm[]                 = [];
	let advisor:       DouAdvisorResponse | null = null;
	let enrollments:   DouEnrollment[]           = [];
	let totalAkts      = 0;
	let grades:        DouGradeEntry[]           = [];
	let gpaTerms:      unknown[]                 = [];
	let cumulativeGpa: number | null             = null;
	let transcript:    unknown[] | null          = null;
	let attendance:    DouAttendanceRow[]        = [];
	let exams:         DouExam[]                 = [];
	let schedule:      DouScheduleRow[]          = [];
	let announcements: DouAnnouncement[]         = [];
	let inboxMsgs:     DouMessage[]              = [];
	let sentMsgs:      DouMessage[]              = [];
	let docRequests:   DouDocumentRequest[]      = [];

	// Yeni veri alanları
	let graduation:     DouGraduationStatus | null  = null;
	let financial:      DouFinancialInfo | null      = null;
	let curriculum:     DouCurriculumStatus | null   = null;
	let todoItems:      DouTodoItem[]                = [];
	let applications:   DouApplication[]             = [];
	let internships:    DouInternship[]              = [];
	let creditTransfers: DouCreditTransfer[]         = [];
	let prepSchedule:   DouPrepScheduleRow[]         = [];
	let prepExams:      DouPrepExam[]                = [];
	let prepGrades:     DouPrepGrade[]               = [];
	let prepAttendance: DouPrepAttendanceRow[]       = [];

	// Belge talebi form
	let docForm = { requesting_institution: '', request_reason: '', document_type: 'öğrenci_belgesi', document_subtype: 'Türkçe' };
	let docSubmitting = false;
	let docSuccess: string | null = null;
	let docError: string | null = null;

	const DOC_SUBTYPES: Record<string, string[]> = {
		'transkript':       ['Resmi', 'Onaysız'],
		'öğrenci_belgesi':  ['Türkçe', 'İngilizce'],
		'disiplin_belgesi': ['Türkçe', 'İngilizce'],
	};
	$: docSubtypes = DOC_SUBTYPES[docForm.document_type] ?? ['Türkçe'];

	// Başvuru formu state
	let appForm = { course_code: '', notes: '' };
	let appSubmitting = false;
	let appSuccess: string | null = null;
	let appError: string | null = null;

	// Staj formu state
	let intForm = { company_name: '', company_address: '', supervisor_name: '', supervisor_email: '', start_date: '', end_date: '', internship_type: 'zorunlu', notes: '' };
	let intSubmitting = false;
	let intSuccess: string | null = null;
	let intError: string | null = null;

	// İntibak formu state
	let ctForm = { source_institution: '', source_course_code: '', source_course_name: '', source_credits: 3, target_course_code: '', target_course_name: '', notes: '' };
	let ctSubmitting = false;
	let ctSuccess: string | null = null;
	let ctError: string | null = null;

	// Şifre değiştirme formu state
	let pwForm = { current_password: '', new_password: '', new_password_confirm: '' };
	let pwSubmitting = false;
	let pwSuccess: string | null = null;
	let pwError: string | null = null;

	async function loadPage(path: string) {
		if (!browser || !apiKey) return;
		loading  = true;
		loadErr  = null;
		const token = localStorage.token ?? null;
		if (!token) { loadErr = 'Giriş yapın.'; loading = false; return; }

		try {
			if (apiKey === 'profile' || apiKey === 'transcript') {
				profile = await getDouStudentProfile(token);
			}
			if (apiKey === 'terms') {
				terms = await getDouTerms(token);
			}
			if (apiKey === 'advisor') {
				advisor = await getDouStudentAdvisor(token);
			}
			if (apiKey === 'enrollments') {
				const r = await getDouStudentEnrollments(token);
				enrollments = r.enrollments;
				totalAkts   = r.total_akts ?? 0;
			}
			if (apiKey === 'grades') {
				const r = await getDouStudentGrades(token);
				grades = r.grades;
			}
			if (apiKey === 'gpa') {
				const r = await getDouStudentGpaSummary(token);
				gpaTerms     = r.terms;
				cumulativeGpa = r.cumulative_gpa;
			}
			if (apiKey === 'transcript') {
				const r = await getDouStudentTranscript(token);
				transcript = r.transcript;
				cumulativeGpa = r.cumulative_gpa;
			}
			if (apiKey === 'attendance') {
				const r = await getDouStudentAttendance(token);
				attendance = r.attendance;
			}
			if (apiKey === 'exams') {
				const r = await getDouStudentExams(token);
				exams = r.exams;
			}
			if (apiKey === 'schedule') {
				const r = await getDouStudentSchedule(token);
				schedule = r.schedule;
			}
			if (apiKey === 'announcements') {
				const r = await getDouAnnouncements(token);
				announcements = r.announcements;
			}
			if (apiKey === 'inbox') {
				const r = await getDouInbox(token);
				inboxMsgs = r.messages;
			}
			if (apiKey === 'sent') {
				const r = await getDouSent(token);
				sentMsgs = r.messages;
			}
			if (apiKey === 'doc-request') {
				const r = await getDouStudentDocumentRequests(token);
				docRequests = r.requests;
			}
			if (apiKey === 'graduation') {
				graduation = await getDouGraduationStatus(token);
			}
			if (apiKey === 'financial') {
				financial = await getDouFinancialInfo(token);
			}
			if (apiKey === 'curriculum') {
				curriculum = await getDouCurriculumStatus(token);
			}
			if (apiKey === 'todo') {
				const r = await getDouTodoList(token);
				todoItems = r.todos;
			}
			if (apiKey === 'applications' || apiKey === 'application-form') {
				const r = await getDouApplications(token, appType || undefined);
				applications = r.applications;
			}
			if (apiKey === 'internship') {
				const r = await getDouInternships(token);
				internships = r.internships;
			}
			if (apiKey === 'credit-transfer') {
				const r = await getDouCreditTransfers(token);
				creditTransfers = r.transfers;
			}
			if (apiKey === 'prep-schedule') {
				const r = await getDouPrepSchedule(token);
				prepSchedule = r.schedule;
			}
			if (apiKey === 'prep-exams') {
				const r = await getDouPrepExams(token);
				prepExams = r.exams;
			}
			if (apiKey === 'prep-grades') {
				const r = await getDouPrepGrades(token);
				prepGrades = r.grades;
			}
			if (apiKey === 'prep-attendance') {
				const r = await getDouPrepAttendance(token);
				prepAttendance = r.attendance;
			}
		} catch (e: unknown) {
			loadErr = e instanceof Error ? e.message : 'API hatası.';
		} finally {
			loading = false;
		}
	}

	async function submitApplication() {
		appSubmitting = true; appSuccess = null; appError = null;
		const token = localStorage.token ?? null;
		try {
			await createDouApplication(token, { application_type: appType, course_code: appForm.course_code || undefined, notes: appForm.notes });
			appSuccess = 'Başvurunuz alındı. Durum: bekliyor.';
			appForm = { course_code: '', notes: '' };
			const r = await getDouApplications(token, appType || undefined);
			applications = r.applications;
		} catch (e: unknown) {
			appError = e instanceof Error ? e.message : 'Gönderim hatası.';
		} finally { appSubmitting = false; }
	}

	async function submitInternship() {
		intSubmitting = true; intSuccess = null; intError = null;
		const token = localStorage.token ?? null;
		try {
			await createDouInternship(token, { ...intForm });
			intSuccess = 'Staj başvurunuz alındı.';
			intForm = { company_name: '', company_address: '', supervisor_name: '', supervisor_email: '', start_date: '', end_date: '', internship_type: 'zorunlu', notes: '' };
			const r = await getDouInternships(token);
			internships = r.internships;
		} catch (e: unknown) {
			intError = e instanceof Error ? e.message : 'Gönderim hatası.';
		} finally { intSubmitting = false; }
	}

	async function submitCreditTransfer() {
		ctSubmitting = true; ctSuccess = null; ctError = null;
		const token = localStorage.token ?? null;
		try {
			await createDouCreditTransfer(token, { ...ctForm });
			ctSuccess = 'İntibak başvurunuz alındı.';
			ctForm = { source_institution: '', source_course_code: '', source_course_name: '', source_credits: 3, target_course_code: '', target_course_name: '', notes: '' };
			const r = await getDouCreditTransfers(token);
			creditTransfers = r.transfers;
		} catch (e: unknown) {
			ctError = e instanceof Error ? e.message : 'Gönderim hatası.';
		} finally { ctSubmitting = false; }
	}

	function submitPassword() {
		pwSubmitting = true; pwSuccess = null; pwError = null;
		setTimeout(() => {
			if (!pwForm.current_password || !pwForm.new_password) {
				pwError = 'Tüm alanları doldurun.';
			} else if (pwForm.new_password !== pwForm.new_password_confirm) {
				pwError = 'Yeni şifreler eşleşmiyor.';
			} else if (pwForm.new_password.length < 8) {
				pwError = 'Yeni şifre en az 8 karakter olmalı.';
			} else {
				pwSuccess = 'Şifre başarıyla güncellendi. (Mock — gerçek DB bağlantısı Faz 4\'te eklenecek.)';
				pwForm = { current_password: '', new_password: '', new_password_confirm: '' };
			}
			pwSubmitting = false;
		}, 400);
	}

	async function submitDocRequest() {
		docSubmitting = true; docSuccess = null; docError = null;
		const token = localStorage.token ?? null;
		try {
			await createDouDocumentRequest(token, { ...docForm });
			docSuccess = 'Belge talebiniz alındı. Durum: bekliyor.';
			const r = await getDouStudentDocumentRequests(token);
			docRequests = r.requests;
		} catch (e: unknown) {
			docError = e instanceof Error ? e.message : 'Gönderim hatası.';
		} finally {
			docSubmitting = false;
		}
	}

	$: if (browser) loadPage(activePath);
	afterNavigate(() => loadPage(activePath));
</script>

<svelte:head><title>OBS • {pageTitle}</title></svelte:head>

<ObsShell {activePath}>
	<span slot="userline">{$user?.name ?? 'Kullanıcı'} • OBS</span>

	<div class="space-y-4">
		<!-- Başlık -->
		<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
			<div class="text-sm font-semibold">{pageTitle}</div>
			<div class="mt-1 text-xs text-slate-500 dark:text-slate-300">{hint}</div>
		</div>

		<!-- Yükleniyor / Hata -->
		{#if loading}
			<div class="rounded-2xl border border-black/10 bg-white p-8 text-center text-sm text-slate-400 shadow-sm dark:border-white/10 dark:bg-white/5">Yükleniyor…</div>
		{:else if loadErr}
			<div class="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-900/40 dark:bg-amber-950/30">
				<div class="text-sm font-semibold text-amber-900 dark:text-amber-100">API bağlantı hatası</div>
				<div class="mt-1 text-xs text-amber-800 dark:text-amber-200">{loadErr}</div>
				{#if loadErr.includes('JSON döndürmedi')}
					<div class="mt-2 text-xs text-amber-700 dark:text-amber-300">
						Backend yeniden başlatılması gerekiyor olabilir — yeni mock route'lar ancak restart sonrası aktif olur.
					</div>
				{/if}
			</div>

		<!-- ============================================================ -->
		<!-- PROFİL / ÖZLÜK                                               -->
		<!-- ============================================================ -->
		{:else if (apiKey === 'profile') && profile}
			<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
				{#each [
					['Öğrenci No', profile.student_no],
					['Ad Soyad', profile.full_name ?? '—'],
					['E-posta', profile.email],
					['Bölüm', profile.department_name],
					['Fakülte', profile.faculty_name ?? '—'],
					['Program', profile.program],
					['Sınıf', String(profile.class_level)],
					['GPA', profile.gpa != null ? profile.gpa.toFixed(2) : '—'],
					['Kayıt Tarihi', profile.enrollment_date ?? '—'],
					['Durum', profile.status ?? '—'],
					['Mali Uygunluk', profile.is_financially_eligible ? '✓ Uygun' : '✗ Uygun Değil'],
				] as [lbl, val]}
					<div class="rounded-xl border border-black/10 bg-slate-50 p-4 dark:border-white/10 dark:bg-white/5">
						<div class="text-xs font-semibold text-slate-500 dark:text-slate-400">{lbl}</div>
						<div class="mt-1 text-sm font-medium">{val}</div>
					</div>
				{/each}
			</div>

		<!-- ============================================================ -->
		<!-- AKADEMİK TAKVİM                                              -->
		<!-- ============================================================ -->
		{:else if apiKey === 'terms' && terms.length}
			<div class="overflow-hidden rounded-2xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="grid grid-cols-5 bg-slate-50 px-5 py-3 text-xs font-semibold text-slate-600 dark:bg-white/5 dark:text-slate-300">
					<div class="col-span-2">Dönem</div><div>Yıl</div><div>Başlangıç</div><div>Bitiş</div>
				</div>
				{#each terms as t}
					<div class="grid grid-cols-5 border-t border-black/5 px-5 py-3 text-sm dark:border-white/10 {t.is_active ? 'bg-sky-50/60 dark:bg-sky-900/10' : ''}">
						<div class="col-span-2 font-medium">{t.name} {#if t.is_active}<span class="ml-2 rounded-full bg-sky-100 px-2 py-0.5 text-xs text-sky-700 dark:bg-sky-900/40 dark:text-sky-300">Aktif</span>{/if}</div>
						<div>{t.academic_year}</div><div>{t.starts_at}</div><div>{t.ends_at}</div>
					</div>
				{/each}
			</div>

		<!-- ============================================================ -->
		<!-- DANIŞMAN BİLGİLERİ                                           -->
		<!-- ============================================================ -->
		{:else if apiKey === 'advisor' && advisor?.advisor}
			<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="flex items-start gap-4">
					<div class="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-sky-100 text-xl font-bold text-sky-700 dark:bg-sky-900/40 dark:text-sky-300">
						{advisor.advisor.name.charAt(0)}
					</div>
					<div>
						<div class="text-base font-semibold">{advisor.advisor.name}</div>
						{#if advisor.advisor.title}<div class="text-xs text-slate-500">{advisor.advisor.title}</div>{/if}
					</div>
				</div>
				<div class="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2 text-sm">
					<div><span class="font-medium text-slate-500">E-posta: </span><a href="mailto:{advisor.advisor.email}" class="text-sky-600 hover:underline dark:text-sky-400">{advisor.advisor.email}</a></div>
					{#if advisor.advisor.office}<div><span class="font-medium text-slate-500">Oda: </span>{advisor.advisor.office}</div>{/if}
					{#if advisor.advisor.phone}<div><span class="font-medium text-slate-500">Tel: </span>{advisor.advisor.phone}</div>{/if}
					{#if advisor.advisor.department_name}<div><span class="font-medium text-slate-500">Bölüm: </span>{advisor.advisor.department_name}</div>{/if}
					{#if advisor.valid_from}<div><span class="font-medium text-slate-500">Atama: </span>{advisor.valid_from}</div>{/if}
				</div>
			</div>

		<!-- ============================================================ -->
		<!-- ALINAN DERSLER                                                -->
		<!-- ============================================================ -->
		{:else if apiKey === 'enrollments'}
			{#if enrollments.length}
				<div class="rounded-2xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5">
					<div class="flex items-center justify-between px-5 py-3 text-xs font-semibold text-slate-500">
						<span>Toplam {enrollments.length} ders</span>
						<span>Toplam AKTS: <strong class="text-slate-800 dark:text-slate-100">{totalAkts}</strong></span>
					</div>
					<div class="overflow-x-auto">
						<table class="w-full text-sm">
							<thead class="bg-slate-50 text-xs text-slate-600 dark:bg-white/5 dark:text-slate-300">
								<tr>
									<th class="px-4 py-3 text-left">Kod</th>
									<th class="px-4 py-3 text-left">Ders Adı</th>
									<th class="px-4 py-3 text-center">K</th>
									<th class="px-4 py-3 text-center">AKTS</th>
									<th class="px-4 py-3 text-left">Öğr. Elemanı</th>
									<th class="px-4 py-3 text-left">Gün / Saat</th>
									<th class="px-4 py-3 text-left">Derslik</th>
								</tr>
							</thead>
							<tbody>
								{#each enrollments as e}
									<tr class="border-t border-black/5 dark:border-white/10">
										<td class="px-4 py-3 font-mono text-xs">{e.course_code}</td>
										<td class="px-4 py-3">{e.course_name}</td>
										<td class="px-4 py-3 text-center">{e.credits}</td>
										<td class="px-4 py-3 text-center">{e.akts}</td>
										<td class="px-4 py-3 text-xs text-slate-500">{e.instructor_name ?? '—'}</td>
										<td class="px-4 py-3 text-xs">{e.day_of_week ?? '—'} {e.start_time ?? ''}–{e.end_time ?? ''}</td>
										<td class="px-4 py-3 text-xs">{e.classroom ?? '—'}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				</div>
			{:else}
				<div class="rounded-2xl border border-dashed border-black/15 bg-slate-50 p-6 text-center text-sm text-slate-400 dark:border-white/15 dark:bg-white/5">Kayıtlı ders bulunamadı.</div>
			{/if}

		<!-- ============================================================ -->
		<!-- SINAV TAKVİMİ                                                 -->
		<!-- ============================================================ -->
		{:else if apiKey === 'exams'}
			<div class="overflow-hidden rounded-2xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead class="bg-slate-50 text-xs text-slate-600 dark:bg-white/5 dark:text-slate-300">
							<tr>
								<th class="px-4 py-3 text-left">Ders</th>
								<th class="px-4 py-3 text-left">Tür</th>
								<th class="px-4 py-3 text-left">Tarih</th>
								<th class="px-4 py-3 text-left">Saat</th>
								<th class="px-4 py-3 text-left">Derslik</th>
								<th class="px-4 py-3 text-center">Ağırlık</th>
							</tr>
						</thead>
						<tbody>
							{#each exams as ex}
								<tr class="border-t border-black/5 dark:border-white/10">
									<td class="px-4 py-3 font-mono text-xs">{ex.course_code}</td>
									<td class="px-4 py-3">
										<span class="rounded-full px-2 py-0.5 text-xs font-medium
											{ex.exam_type === 'midterm' ? 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300' :
											 ex.exam_type === 'final'   ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' :
											                              'bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-300'}">
											{ex.exam_type === 'midterm' ? 'Vize' : ex.exam_type === 'final' ? 'Final' : ex.exam_type}
										</span>
									</td>
									<td class="px-4 py-3">{ex.exam_date}</td>
									<td class="px-4 py-3">{ex.exam_time}</td>
									<td class="px-4 py-3 text-xs">{ex.classroom}</td>
									<td class="px-4 py-3 text-center">%{ex.weight_percent}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>

		<!-- ============================================================ -->
		<!-- DERS PROGRAMI                                                 -->
		<!-- ============================================================ -->
		{:else if apiKey === 'schedule'}
			{@const days = ['Pazartesi','Salı','Çarşamba','Perşembe','Cuma']}
			<div class="space-y-2">
				{#each days as day}
					{@const dayRows = schedule.filter(s => s.day === day)}
					{#if dayRows.length}
						<div class="rounded-xl border border-black/10 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/5">
							<div class="mb-3 text-xs font-semibold text-slate-500">{day}</div>
							{#each dayRows as s}
								<div class="mb-2 flex items-center gap-3 rounded-lg bg-sky-50 px-4 py-2.5 dark:bg-sky-900/20">
									<span class="w-28 shrink-0 text-xs text-slate-500">{s.start}–{s.end}</span>
									<span class="font-mono text-xs font-semibold">{s.course_code}</span>
									<span class="flex-1 text-sm">{s.course_name}</span>
									<span class="text-xs text-slate-400">{s.classroom}</span>
								</div>
							{/each}
						</div>
					{/if}
				{/each}
			</div>

		<!-- ============================================================ -->
		<!-- NOT LİSTESİ                                                   -->
		<!-- ============================================================ -->
		{:else if apiKey === 'grades'}
			<div class="overflow-hidden rounded-2xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead class="bg-slate-50 text-xs text-slate-600 dark:bg-white/5 dark:text-slate-300">
							<tr>
								<th class="px-4 py-3 text-left">Ders</th>
								<th class="px-4 py-3 text-center">Vize</th>
								<th class="px-4 py-3 text-center">Final</th>
								<th class="px-4 py-3 text-center">Harf</th>
								<th class="px-4 py-3 text-center">Durum</th>
							</tr>
						</thead>
						<tbody>
							{#each grades as g}
								<tr class="border-t border-black/5 dark:border-white/10">
									<td class="px-4 py-3 font-mono text-xs">{g.course_code}</td>
									<td class="px-4 py-3 text-center">{g.midterm ?? '—'}</td>
									<td class="px-4 py-3 text-center">{g.final ?? '—'}</td>
									<td class="px-4 py-3 text-center font-semibold">
										{#if g.is_published && g.letter_grade}
											<span class="rounded-full bg-emerald-100 px-2.5 py-0.5 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">{g.letter_grade}</span>
										{:else}—{/if}
									</td>
									<td class="px-4 py-3 text-center text-xs">
										{#if g.is_published}<span class="text-emerald-600">Yayınlandı</span>
										{:else if g.is_finalized}<span class="text-amber-600">Kesinleşti</span>
										{:else}<span class="text-slate-400">Bekleniyor</span>{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>

		<!-- ============================================================ -->
		<!-- DÖNEM ORTALAMALARI                                            -->
		<!-- ============================================================ -->
		{:else if apiKey === 'gpa'}
			<div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
				<div class="col-span-1 rounded-2xl border border-black/10 bg-white p-5 text-center shadow-sm dark:border-white/10 dark:bg-white/5 sm:col-span-1">
					<div class="text-xs font-semibold text-slate-500">Kümülatif GNO</div>
					<div class="mt-2 text-4xl font-bold text-sky-600 dark:text-sky-400">{cumulativeGpa?.toFixed(2) ?? '—'}</div>
				</div>
				<div class="col-span-1 overflow-hidden rounded-2xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5 sm:col-span-2">
					<div class="grid grid-cols-3 bg-slate-50 px-5 py-3 text-xs font-semibold text-slate-600 dark:bg-white/5 dark:text-slate-300">
						<div>Dönem</div><div class="text-center">DNO</div><div class="text-center">AKTS</div>
					</div>
					{#each (gpaTerms as {term_name:string; term_gpa:number|null; akts_completed:number}[]) as t}
						<div class="grid grid-cols-3 border-t border-black/5 px-5 py-3 text-sm dark:border-white/10">
							<div>{t.term_name}</div>
							<div class="text-center font-semibold">{t.term_gpa?.toFixed(2) ?? '—'}</div>
							<div class="text-center">{t.akts_completed}</div>
						</div>
					{/each}
				</div>
			</div>

		<!-- ============================================================ -->
		<!-- TRANSKRİPT                                                    -->
		<!-- ============================================================ -->
		{:else if apiKey === 'transcript' && transcript}
			<div class="mb-3 flex items-center justify-between">
				<div class="text-sm font-semibold">Kümülatif GNO: <span class="text-sky-600 dark:text-sky-400">{cumulativeGpa?.toFixed(2) ?? '—'}</span></div>
				<button class="rounded-xl border border-black/10 px-3 py-1.5 text-xs font-medium hover:bg-slate-50 dark:border-white/10 dark:hover:bg-white/5" on:click={() => window.print()}>
					Yazdır
				</button>
			</div>
			{#each (transcript as {term_name:string; term_gpa:number; term_akts:number; courses:{code:string;name:string;credits:number;akts:number;letter:string;grade_point:number}[]}[]) as term}
				<div class="mb-4 overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5">
					<div class="flex items-center justify-between bg-slate-100 px-5 py-3 dark:bg-white/10">
						<div class="text-sm font-semibold">{term.term_name}</div>
						<div class="text-xs text-slate-500">DNO: <strong>{term.term_gpa.toFixed(2)}</strong> · AKTS: {term.term_akts}</div>
					</div>
					{#each term.courses as c}
						<div class="grid grid-cols-5 border-t border-black/5 px-5 py-2.5 text-sm dark:border-white/10">
							<div class="font-mono text-xs">{c.code}</div>
							<div class="col-span-2">{c.name}</div>
							<div class="text-center text-xs text-slate-500">{c.credits}K / {c.akts}AKTS</div>
							<div class="text-center font-semibold">{c.letter}</div>
						</div>
					{/each}
				</div>
			{/each}

		<!-- ============================================================ -->
		<!-- DEVAMSIZLIK                                                    -->
		<!-- ============================================================ -->
		{:else if apiKey === 'attendance'}
			<div class="overflow-hidden rounded-2xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead class="bg-slate-50 text-xs text-slate-600 dark:bg-white/5 dark:text-slate-300">
							<tr>
								<th class="px-4 py-3 text-left">Ders</th>
								<th class="px-4 py-3 text-center">Toplam Hafta</th>
								<th class="px-4 py-3 text-center">Devamsız</th>
								<th class="px-4 py-3 text-center">Devam %</th>
								<th class="px-4 py-3 text-center">Durum</th>
							</tr>
						</thead>
						<tbody>
							{#each attendance as a}
								<tr class="border-t border-black/5 dark:border-white/10">
									<td class="px-4 py-3">
										<div class="font-mono text-xs font-semibold">{a.course_code}</div>
										<div class="text-xs text-slate-500">{a.course_name}</div>
									</td>
									<td class="px-4 py-3 text-center">{a.total_weeks}</td>
									<td class="px-4 py-3 text-center">{a.absent_count}</td>
									<td class="px-4 py-3 text-center font-semibold">%{a.attendance_pct.toFixed(1)}</td>
									<td class="px-4 py-3 text-center">
										{#if a.status === 'ok'}
											<span class="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">İyi</span>
										{:else if a.status === 'warning'}
											<span class="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">Uyarı</span>
										{:else}
											<span class="rounded-full bg-red-100 px-2.5 py-0.5 text-xs text-red-700 dark:bg-red-900/40 dark:text-red-300">Kritik</span>
										{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>

		<!-- ============================================================ -->
		<!-- DUYURULAR                                                     -->
		<!-- ============================================================ -->
		{:else if apiKey === 'announcements'}
			{#if announcements.length}
				<div class="space-y-3">
					{#each announcements as ann}
						<div class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
							<div class="flex items-start justify-between gap-3">
								<div class="text-sm font-semibold">{ann.title}</div>
								<span class="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-white/10 dark:text-slate-300">
									{ann.audience_type === 'all' ? 'Genel' : 'Bölüm'}
								</span>
							</div>
							<div class="mt-2 text-sm text-slate-600 dark:text-slate-300">{ann.content}</div>
							<div class="mt-2 text-xs text-slate-400">{ann.published_at ?? ''} · {ann.created_by ?? ''}</div>
						</div>
					{/each}
				</div>
			{:else}
				<div class="rounded-2xl border border-dashed border-black/15 bg-slate-50 p-6 text-center text-sm text-slate-400 dark:border-white/15 dark:bg-white/5">Henüz duyuru yok.</div>
			{/if}

		<!-- ============================================================ -->
		<!-- GELEN MESAJLAR                                                -->
		<!-- ============================================================ -->
		{:else if apiKey === 'inbox'}
			<div class="space-y-3">
				{#each inboxMsgs.filter(m => m.status !== 'deleted') as m}
					<div class="rounded-xl border bg-white p-5 shadow-sm {m.is_read ? 'border-black/10 dark:border-white/10' : 'border-sky-200 dark:border-sky-800'} dark:bg-white/5">
						<div class="flex items-start justify-between gap-3">
							<div class="font-medium text-sm {m.is_read ? '' : 'font-bold'}">{m.subject}</div>
							{#if !m.is_read}<span class="h-2 w-2 shrink-0 rounded-full bg-sky-500 mt-1.5"></span>{/if}
						</div>
						<div class="mt-1 text-xs text-slate-500">{m.sender_name ?? m.sender_type} · {m.sent_at}</div>
						<div class="mt-2 text-sm text-slate-600 dark:text-slate-300">{m.body}</div>
					</div>
				{:else}
					<div class="rounded-2xl border border-dashed border-black/15 bg-slate-50 p-6 text-center text-sm text-slate-400 dark:border-white/15 dark:bg-white/5">Gelen kutunuz boş.</div>
				{/each}
			</div>

		<!-- ============================================================ -->
		<!-- GÖNDERİLEN MESAJLAR                                           -->
		<!-- ============================================================ -->
		{:else if apiKey === 'sent'}
			<div class="space-y-3">
				{#each sentMsgs.filter(m => m.status !== 'deleted') as m}
					<div class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
						<div class="text-sm font-medium">{m.subject}</div>
						<div class="mt-1 text-xs text-slate-500">→ {m.receiver_name ?? m.receiver_type} · {m.sent_at}</div>
						<div class="mt-2 text-sm text-slate-600 dark:text-slate-300">{m.body}</div>
					</div>
				{:else}
					<div class="rounded-2xl border border-dashed border-black/15 bg-slate-50 p-6 text-center text-sm text-slate-400 dark:border-white/15 dark:bg-white/5">Gönderilen mesaj yok.</div>
				{/each}
			</div>

		<!-- ============================================================ -->
		<!-- BELGE TALEBİ                                                  -->
		<!-- ============================================================ -->
		{:else if apiKey === 'doc-request'}
			<div class="grid grid-cols-1 gap-5 lg:grid-cols-2">
				<!-- Form -->
				<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
					<div class="mb-4 text-sm font-semibold">Yeni Belge Talebi</div>
					{#if docSuccess}
						<div class="mb-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200">{docSuccess}</div>
					{/if}
					{#if docError}
						<div class="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-200">{docError}</div>
					{/if}
					<div class="space-y-3">
						<label class="block">
							<div class="text-xs font-semibold text-slate-500">Talep Eden Kurum</div>
							<input bind:value={docForm.requesting_institution} class="mt-1 w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-white/5" placeholder="Kurum adı" />
						</label>
						<label class="block">
							<div class="text-xs font-semibold text-slate-500">Talep Nedeni</div>
							<input bind:value={docForm.request_reason} class="mt-1 w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-white/5" placeholder="Neden" />
						</label>
						<label class="block">
							<div class="text-xs font-semibold text-slate-500">Belge Türü</div>
							<select bind:value={docForm.document_type} class="mt-1 w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-white/5">
								<option value="öğrenci_belgesi">Öğrenci Belgesi</option>
								<option value="transkript">Transkript</option>
								<option value="disiplin_belgesi">Disiplin Belgesi</option>
							</select>
						</label>
						<label class="block">
							<div class="text-xs font-semibold text-slate-500">Belge Tipi</div>
							<select bind:value={docForm.document_subtype} class="mt-1 w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-white/5">
								{#each docSubtypes as sub}<option value={sub}>{sub}</option>{/each}
							</select>
						</label>
						<button on:click={submitDocRequest} disabled={docSubmitting} type="button" class="w-full rounded-xl bg-sky-500 py-2 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50">
							{docSubmitting ? 'Gönderiliyor…' : 'Talep Gönder'}
						</button>
					</div>
				</div>

				<!-- Geçmiş talepler -->
				<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
					<div class="mb-4 text-sm font-semibold">Geçmiş Talepler</div>
					{#if docRequests.length}
						<div class="space-y-2">
							{#each docRequests as req}
								<div class="rounded-xl border border-black/10 p-3 text-sm dark:border-white/10">
									<div class="flex items-center justify-between">
										<span class="font-medium">{req.document_type} — {req.document_subtype}</span>
										<span class="rounded-full px-2 py-0.5 text-xs {req.status === 'tamamlandı' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' : 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'}">{req.status}</span>
									</div>
									<div class="mt-1 text-xs text-slate-500">{req.requesting_institution} · {req.created_at?.slice(0,10)}</div>
								</div>
							{/each}
						</div>
					{:else}
						<div class="text-sm text-slate-400">Henüz talep yok.</div>
					{/if}
				</div>
			</div>

		<!-- ============================================================ -->
		<!-- MEZUNİYET ONAY                                               -->
		<!-- ============================================================ -->
		{:else if apiKey === 'graduation' && graduation}
			<div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
				<div class="rounded-2xl border border-black/10 bg-white p-5 text-center shadow-sm dark:border-white/10 dark:bg-white/5">
					<div class="text-xs font-semibold text-slate-500">Kümülatif GNO</div>
					<div class="mt-2 text-4xl font-bold text-sky-600 dark:text-sky-400">{graduation.cumulative_gpa.toFixed(2)}</div>
				</div>
				<div class="rounded-2xl border border-black/10 bg-white p-5 text-center shadow-sm dark:border-white/10 dark:bg-white/5">
					<div class="text-xs font-semibold text-slate-500">AKTS İlerlemesi</div>
					<div class="mt-2 text-2xl font-bold">{graduation.total_akts_completed} <span class="text-base font-normal text-slate-400">/ {graduation.total_akts_required}</span></div>
					<div class="mt-1 h-2 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-white/10">
						<div class="h-2 rounded-full bg-sky-500" style="width:{Math.min(100, graduation.total_akts_completed / graduation.total_akts_required * 100).toFixed(1)}%"></div>
					</div>
				</div>
				<div class="rounded-2xl border p-5 text-center shadow-sm {graduation.eligible_for_graduation ? 'border-emerald-200 bg-emerald-50 dark:border-emerald-900/40 dark:bg-emerald-950/30' : 'border-amber-200 bg-amber-50 dark:border-amber-900/40 dark:bg-amber-950/30'}">
					<div class="text-xs font-semibold text-slate-500">Durum</div>
					<div class="mt-2 text-base font-semibold {graduation.eligible_for_graduation ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-300'}">{graduation.status_label}</div>
					{#if !graduation.eligible_for_graduation}
						<div class="mt-1 text-xs text-amber-600 dark:text-amber-400">Eksik: {graduation.missing_akts} AKTS</div>
					{/if}
				</div>
			</div>
			<div class="overflow-hidden rounded-2xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="px-5 py-3 text-sm font-semibold">Gereksinim Durumu</div>
				<div class="grid grid-cols-4 bg-slate-50 px-5 py-2 text-xs font-semibold text-slate-500 dark:bg-white/5">
					<div class="col-span-2">Kategori</div><div class="text-center">Ders</div><div class="text-center">AKTS</div>
				</div>
				{#each graduation.requirements as req}
					<div class="grid grid-cols-4 border-t border-black/5 px-5 py-3 text-sm dark:border-white/10">
						<div class="col-span-2 flex items-center gap-2">
							<span class="h-2 w-2 rounded-full {req.met ? 'bg-emerald-500' : 'bg-amber-400'}"></span>{req.category}
						</div>
						<div class="text-center text-xs">{req.completed}/{req.required}</div>
						<div class="text-center text-xs">{req.akts_completed}/{req.akts_required}</div>
					</div>
				{/each}
			</div>
			<div class="overflow-hidden rounded-2xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="px-5 py-3 text-sm font-semibold">Onay Adımları</div>
				{#each graduation.approval_steps as step}
					<div class="flex items-center justify-between border-t border-black/5 px-5 py-3 text-sm dark:border-white/10">
						<span>{step.step}</span>
						<span class="rounded-full px-2.5 py-0.5 text-xs
							{step.status === 'approved' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' :
							 step.status === 'rejected' ? 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300' :
							                              'bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-300'}">
							{step.status === 'approved' ? 'Onaylandı' : step.status === 'rejected' ? 'Reddedildi' : 'Bekliyor'}
						</span>
					</div>
				{/each}
			</div>

		<!-- ============================================================ -->
		<!-- HARÇ BİLGİLERİ                                               -->
		<!-- ============================================================ -->
		{:else if apiKey === 'financial' && financial}
			<div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
				<div class="rounded-2xl border border-black/10 bg-white p-5 text-center shadow-sm dark:border-white/10 dark:bg-white/5">
					<div class="text-xs font-semibold text-slate-500">Toplam Ödeme</div>
					<div class="mt-2 text-3xl font-bold text-sky-600 dark:text-sky-400">₺{financial.total_paid.toLocaleString('tr-TR')}</div>
				</div>
				<div class="rounded-2xl border border-black/10 bg-white p-5 text-center shadow-sm dark:border-white/10 dark:bg-white/5">
					<div class="text-xs font-semibold text-slate-500">Burs / İndirim</div>
					<div class="mt-2 text-3xl font-bold text-emerald-600 dark:text-emerald-400">₺{financial.total_scholarship.toLocaleString('tr-TR')}</div>
				</div>
				<div class="rounded-2xl border p-5 text-center shadow-sm {financial.is_financially_eligible ? 'border-emerald-200 bg-emerald-50 dark:border-emerald-900/40 dark:bg-emerald-950/30' : 'border-red-200 bg-red-50 dark:border-red-900/40 dark:bg-red-950/30'}">
					<div class="text-xs font-semibold text-slate-500">Mali Uygunluk</div>
					<div class="mt-2 font-semibold {financial.is_financially_eligible ? 'text-emerald-700 dark:text-emerald-300' : 'text-red-700 dark:text-red-300'}">
						{financial.is_financially_eligible ? '✓ Uygun' : '✗ Uygun Değil'}
					</div>
				</div>
			</div>
			<div class="overflow-hidden rounded-2xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="px-5 py-3 text-sm font-semibold">Dönem Harç Bilgileri</div>
				<div class="grid grid-cols-5 bg-slate-50 px-5 py-2 text-xs font-semibold text-slate-500 dark:bg-white/5">
					<div class="col-span-2">Dönem</div><div class="text-right">Harç</div><div class="text-right">Ödenen</div><div class="text-center">Durum</div>
				</div>
				{#each financial.terms as t}
					<div class="grid grid-cols-5 border-t border-black/5 px-5 py-3 text-sm dark:border-white/10">
						<div class="col-span-2">{t.term_name}</div>
						<div class="text-right text-xs">₺{t.tuition_fee.toLocaleString('tr-TR')}</div>
						<div class="text-right text-xs">₺{t.amount_paid.toLocaleString('tr-TR')}</div>
						<div class="text-center">
							<span class="rounded-full px-2 py-0.5 text-xs {t.payment_status === 'ödendi' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' : 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'}">{t.payment_status}</span>
						</div>
					</div>
				{/each}
			</div>
			{#if financial.scholarships.length}
				<div class="overflow-hidden rounded-2xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5">
					<div class="px-5 py-3 text-sm font-semibold">Burs / İndirimler</div>
					{#each financial.scholarships as s}
						<div class="flex items-center justify-between border-t border-black/5 px-5 py-3 text-sm dark:border-white/10">
							<span>{s.name} <span class="ml-1 text-xs text-slate-400">({s.period})</span></span>
							<span class="font-semibold text-emerald-600 dark:text-emerald-400">₺{s.amount.toLocaleString('tr-TR')}</span>
						</div>
					{/each}
				</div>
			{/if}

		<!-- ============================================================ -->
		<!-- MÜFREDAT DURUM                                               -->
		<!-- ============================================================ -->
		{:else if apiKey === 'curriculum' && curriculum}
			<div class="mb-2 flex items-center justify-between rounded-2xl border border-black/10 bg-white px-5 py-4 shadow-sm dark:border-white/10 dark:bg-white/5">
				<div>
					<div class="text-sm font-semibold">{curriculum.program}</div>
					<div class="text-xs text-slate-400">{curriculum.catalog_year} kataloğu</div>
				</div>
				<div class="text-right">
					<div class="text-2xl font-bold text-sky-600 dark:text-sky-400">%{curriculum.overall_progress_pct.toFixed(1)}</div>
					<div class="text-xs text-slate-400">tamamlandı</div>
				</div>
			</div>
			{#each curriculum.categories as cat}
				<div class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5">
					<div class="bg-slate-50 px-5 py-3 text-xs font-semibold text-slate-600 dark:bg-white/5 dark:text-slate-300">{cat.name}</div>
					{#each cat.courses as c}
						<div class="flex items-center justify-between border-t border-black/5 px-5 py-2.5 text-sm dark:border-white/10">
							<div class="flex items-center gap-3">
								<span class="h-2 w-2 shrink-0 rounded-full
									{c.status === 'tamamlandi' ? 'bg-emerald-500' :
									 c.status === 'devam_ediyor' ? 'bg-sky-500' : 'bg-slate-300 dark:bg-slate-600'}"></span>
								<span class="font-mono text-xs text-slate-500">{c.code}</span>
								<span>{c.name}</span>
							</div>
							<div class="flex items-center gap-3 text-xs text-slate-500">
								<span>{c.akts} AKTS</span>
								{#if c.grade}
									<span class="rounded-full bg-emerald-100 px-2 py-0.5 font-semibold text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">{c.grade}</span>
								{:else if c.status === 'devam_ediyor'}
									<span class="rounded-full bg-sky-100 px-2 py-0.5 text-sky-600 dark:bg-sky-900/40 dark:text-sky-300">Devam Ediyor</span>
								{:else}
									<span class="text-slate-400">Alınmadı</span>
								{/if}
							</div>
						</div>
					{/each}
				</div>
			{/each}

		<!-- ============================================================ -->
		<!-- YAPILACAKLAR LİSTESİ                                         -->
		<!-- ============================================================ -->
		{:else if apiKey === 'todo'}
			<div class="space-y-2">
				{#each todoItems as t}
					{@const priorityMap = { urgent: { label: 'Acil', cls: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300' }, high: { label: 'Yüksek', cls: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300' }, medium: { label: 'Orta', cls: 'bg-sky-100 text-sky-600 dark:bg-sky-900/40 dark:text-sky-300' }, low: { label: 'Düşük', cls: 'bg-slate-100 text-slate-500 dark:bg-white/10 dark:text-slate-400' } }}
					{@const p = priorityMap[t.priority] ?? priorityMap.low}
					<div class="flex items-start gap-3 rounded-xl border border-black/10 bg-white px-4 py-3 shadow-sm dark:border-white/10 dark:bg-white/5 {t.is_done ? 'opacity-50' : ''}">
						<span class="mt-0.5 h-4 w-4 shrink-0 rounded {t.is_done ? 'bg-emerald-500' : 'border-2 border-slate-300 dark:border-white/20'}"></span>
						<div class="flex-1">
							<div class="text-sm {t.is_done ? 'line-through text-slate-400' : 'font-medium'}">{t.title}</div>
							<div class="mt-0.5 text-xs text-slate-400">Son tarih: {t.due_date}</div>
						</div>
						<span class="shrink-0 rounded-full px-2 py-0.5 text-xs {p.cls}">{p.label}</span>
					</div>
				{:else}
					<div class="rounded-2xl border border-dashed border-black/15 bg-slate-50 p-6 text-center text-sm text-slate-400 dark:border-white/15 dark:bg-white/5">Yapılacak yok.</div>
				{/each}
			</div>

		<!-- ============================================================ -->
		<!-- BAŞVURU FORMU (tek ders, ek sınav, ÇAP, yandal vb.)         -->
		<!-- ============================================================ -->
		{:else if apiKey === 'application-form'}
			<div class="grid grid-cols-1 gap-5 lg:grid-cols-2">
				<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
					<div class="mb-4 text-sm font-semibold">Yeni Başvuru — {pageTitle}</div>
					{#if appSuccess}
						<div class="mb-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200">{appSuccess}</div>
					{/if}
					{#if appError}
						<div class="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-200">{appError}</div>
					{/if}
					<div class="space-y-3">
						<label class="block">
							<div class="text-xs font-semibold text-slate-500">Ders Kodu (varsa)</div>
							<input bind:value={appForm.course_code} class="mt-1 w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-white/5" placeholder="Örn. YBS301" />
						</label>
						<label class="block">
							<div class="text-xs font-semibold text-slate-500">Notlar / Gerekçe</div>
							<textarea bind:value={appForm.notes} rows="4" class="mt-1 w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-white/5" placeholder="Açıklama..."></textarea>
						</label>
						<button on:click={submitApplication} disabled={appSubmitting} type="button" class="w-full rounded-xl bg-sky-500 py-2 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50">
							{appSubmitting ? 'Gönderiliyor…' : 'Başvur'}
						</button>
					</div>
				</div>
				<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
					<div class="mb-4 text-sm font-semibold">Geçmiş Başvurular</div>
					{#if applications.length}
						<div class="space-y-2">
							{#each applications as app}
								<div class="rounded-xl border border-black/10 p-3 text-sm dark:border-white/10">
									<div class="flex items-center justify-between">
										<span class="font-medium">{app.application_type.replace(/_/g, ' ')}</span>
										<span class="rounded-full px-2 py-0.5 text-xs {app.status === 'onaylandi' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' : app.status === 'reddedildi' ? 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300' : 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'}">{app.status}</span>
									</div>
									{#if app.course_code}<div class="mt-1 text-xs text-slate-400">Ders: {app.course_code}</div>{/if}
									<div class="text-xs text-slate-400">{app.submitted_at?.slice(0,10)}</div>
								</div>
							{/each}
						</div>
					{:else}
						<div class="text-sm text-slate-400">Henüz başvuru yok.</div>
					{/if}
				</div>
			</div>

		<!-- ============================================================ -->
		<!-- BAŞVURU LİSTESİ (geçmiş / işlemler)                         -->
		<!-- ============================================================ -->
		{:else if apiKey === 'applications'}
			{#if applications.length}
				<div class="space-y-2">
					{#each applications as app}
						<div class="rounded-xl border border-black/10 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/5">
							<div class="flex items-start justify-between gap-3">
								<div class="text-sm font-medium">{app.application_type.replace(/_/g, ' ')}</div>
								<span class="shrink-0 rounded-full px-2 py-0.5 text-xs {app.status === 'onaylandi' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' : app.status === 'reddedildi' ? 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300' : 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'}">{app.status}</span>
							</div>
							{#if app.course_code}<div class="mt-1 text-xs text-slate-400">Ders: {app.course_code}</div>{/if}
							{#if app.notes}<div class="mt-1 text-xs text-slate-500">{app.notes}</div>{/if}
							<div class="mt-1 text-xs text-slate-400">{app.submitted_at?.slice(0,10)}{#if app.reviewed_by} · Değerlendiren: {app.reviewed_by}{/if}</div>
						</div>
					{/each}
				</div>
			{:else}
				<div class="rounded-2xl border border-dashed border-black/15 bg-slate-50 p-6 text-center text-sm text-slate-400 dark:border-white/15 dark:bg-white/5">Henüz başvuru yok.</div>
			{/if}

		<!-- ============================================================ -->
		<!-- STAJ                                                          -->
		<!-- ============================================================ -->
		{:else if apiKey === 'internship'}
			<div class="grid grid-cols-1 gap-5 lg:grid-cols-2">
				<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
					<div class="mb-4 text-sm font-semibold">Staj Başvurusu</div>
					{#if intSuccess}
						<div class="mb-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200">{intSuccess}</div>
					{/if}
					{#if intError}
						<div class="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-200">{intError}</div>
					{/if}
					<div class="space-y-3">
						{#each [['Şirket Adı','company_name','text','Şirket adı'], ['Şirket Adresi','company_address','text','İl / İlçe'], ['Sorumlu Kişi','supervisor_name','text','Ad Soyad'], ['Sorumlu E-posta','supervisor_email','email','ornek@sirket.com']] as [lbl, field, type, ph]}
							<label class="block">
								<div class="text-xs font-semibold text-slate-500">{lbl}</div>
								<input bind:value={intForm[field as keyof typeof intForm]} {type} class="mt-1 w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-white/5" placeholder={ph} />
							</label>
						{/each}
						<div class="grid grid-cols-2 gap-3">
							{#each [['Başlangıç','start_date'], ['Bitiş','end_date']] as [lbl, field]}
								<label class="block">
									<div class="text-xs font-semibold text-slate-500">{lbl}</div>
									<input bind:value={intForm[field as keyof typeof intForm]} type="date" class="mt-1 w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-white/5" />
								</label>
							{/each}
						</div>
						<button on:click={submitInternship} disabled={intSubmitting} type="button" class="w-full rounded-xl bg-sky-500 py-2 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50">
							{intSubmitting ? 'Gönderiliyor…' : 'Başvuru Gönder'}
						</button>
					</div>
				</div>
				<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
					<div class="mb-4 text-sm font-semibold">Staj Geçmişi</div>
					{#if internships.length}
						<div class="space-y-2">
							{#each internships as int}
								<div class="rounded-xl border border-black/10 p-3 text-sm dark:border-white/10">
									<div class="flex items-start justify-between">
										<span class="font-medium">{int.company_name}</span>
										<span class="rounded-full px-2 py-0.5 text-xs {int.status === 'tamamlandi' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' : 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'}">{int.status}</span>
									</div>
									<div class="mt-1 text-xs text-slate-400">{int.start_date} – {int.end_date} · {int.internship_type}</div>
								</div>
							{/each}
						</div>
					{:else}
						<div class="text-sm text-slate-400">Henüz staj kaydı yok.</div>
					{/if}
				</div>
			</div>

		<!-- ============================================================ -->
		<!-- İNTİBAK / KREDİ TRANSFER                                     -->
		<!-- ============================================================ -->
		{:else if apiKey === 'credit-transfer'}
			<div class="grid grid-cols-1 gap-5 lg:grid-cols-2">
				<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
					<div class="mb-4 text-sm font-semibold">Yeni İntibak Başvurusu</div>
					{#if ctSuccess}
						<div class="mb-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200">{ctSuccess}</div>
					{/if}
					{#if ctError}
						<div class="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-200">{ctError}</div>
					{/if}
					<div class="space-y-3">
						<label class="block">
							<div class="text-xs font-semibold text-slate-500">Kaynak Kurum</div>
							<input bind:value={ctForm.source_institution} class="mt-1 w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-white/5" placeholder="Önceki üniversite adı" />
						</label>
						<div class="grid grid-cols-2 gap-3">
							<label class="block">
								<div class="text-xs font-semibold text-slate-500">Kaynak Ders Kodu</div>
								<input bind:value={ctForm.source_course_code} class="mt-1 w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-white/5" placeholder="CS101" />
							</label>
							<label class="block">
								<div class="text-xs font-semibold text-slate-500">Kredi</div>
								<input bind:value={ctForm.source_credits} type="number" min="1" max="10" class="mt-1 w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-white/5" />
							</label>
						</div>
						<label class="block">
							<div class="text-xs font-semibold text-slate-500">Kaynak Ders Adı</div>
							<input bind:value={ctForm.source_course_name} class="mt-1 w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-white/5" placeholder="Ders adı" />
						</label>
						<label class="block">
							<div class="text-xs font-semibold text-slate-500">Eşdeğer Ders Kodu (Kurumda)</div>
							<input bind:value={ctForm.target_course_code} class="mt-1 w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-white/5" placeholder="YBS101" />
						</label>
						<label class="block">
							<div class="text-xs font-semibold text-slate-500">Eşdeğer Ders Adı</div>
							<input bind:value={ctForm.target_course_name} class="mt-1 w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-white/5" placeholder="Ders adı" />
						</label>
						<button on:click={submitCreditTransfer} disabled={ctSubmitting} type="button" class="w-full rounded-xl bg-sky-500 py-2 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50">
							{ctSubmitting ? 'Gönderiliyor…' : 'Başvuru Gönder'}
						</button>
					</div>
				</div>
				<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
					<div class="mb-4 text-sm font-semibold">Geçmiş Başvurular</div>
					{#if creditTransfers.length}
						<div class="space-y-2">
							{#each creditTransfers as ct}
								<div class="rounded-xl border border-black/10 p-3 text-sm dark:border-white/10">
									<div class="flex items-center justify-between">
										<span class="font-mono text-xs">{ct.source_course_code} → {ct.target_course_code}</span>
										<span class="rounded-full px-2 py-0.5 text-xs {ct.status === 'onaylandi' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' : 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'}">{ct.status}</span>
									</div>
									<div class="mt-1 text-xs text-slate-400">{ct.source_institution} · {ct.submitted_at?.slice(0,10)}</div>
								</div>
							{/each}
						</div>
					{:else}
						<div class="text-sm text-slate-400">Henüz başvuru yok.</div>
					{/if}
				</div>
			</div>

		<!-- ============================================================ -->
		<!-- HAZIRLIK — DERS PROGRAMI                                     -->
		<!-- ============================================================ -->
		{:else if apiKey === 'prep-schedule'}
			{@const days = ['Pazartesi','Salı','Çarşamba','Perşembe','Cuma']}
			<div class="space-y-2">
				{#each days as day}
					{@const dayRows = prepSchedule.filter(s => s.day === day)}
					{#if dayRows.length}
						<div class="rounded-xl border border-black/10 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/5">
							<div class="mb-3 text-xs font-semibold text-slate-500">{day}</div>
							{#each dayRows as s}
								<div class="mb-2 flex items-center gap-3 rounded-lg bg-emerald-50 px-4 py-2.5 dark:bg-emerald-900/20">
									<span class="w-28 shrink-0 text-xs text-slate-500">{s.start}–{s.end}</span>
									<span class="font-mono text-xs font-semibold">{s.course_code}</span>
									<span class="flex-1 text-sm">{s.course_name}</span>
									<span class="text-xs text-slate-400">{s.classroom}</span>
								</div>
							{/each}
						</div>
					{/if}
				{/each}
			</div>

		<!-- ============================================================ -->
		<!-- HAZIRLIK — SINAV TAKVİMİ                                     -->
		<!-- ============================================================ -->
		{:else if apiKey === 'prep-exams'}
			<div class="overflow-hidden rounded-2xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead class="bg-slate-50 text-xs text-slate-600 dark:bg-white/5 dark:text-slate-300">
							<tr>
								<th class="px-4 py-3 text-left">Ders</th>
								<th class="px-4 py-3 text-left">Tür</th>
								<th class="px-4 py-3 text-left">Tarih</th>
								<th class="px-4 py-3 text-left">Saat</th>
								<th class="px-4 py-3 text-left">Derslik</th>
								<th class="px-4 py-3 text-center">Ağırlık</th>
							</tr>
						</thead>
						<tbody>
							{#each prepExams as ex}
								<tr class="border-t border-black/5 dark:border-white/10">
									<td class="px-4 py-3 font-mono text-xs">{ex.course_code}</td>
									<td class="px-4 py-3">
										<span class="rounded-full px-2 py-0.5 text-xs font-medium {ex.exam_type === 'midterm' ? 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300' : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'}">
											{ex.exam_type === 'midterm' ? 'Vize' : 'Final'}
										</span>
									</td>
									<td class="px-4 py-3">{ex.exam_date}</td>
									<td class="px-4 py-3">{ex.exam_time}</td>
									<td class="px-4 py-3 text-xs">{ex.classroom}</td>
									<td class="px-4 py-3 text-center">%{ex.weight_percent}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>

		<!-- ============================================================ -->
		<!-- HAZIRLIK — NOT LİSTESİ                                      -->
		<!-- ============================================================ -->
		{:else if apiKey === 'prep-grades'}
			<div class="overflow-hidden rounded-2xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead class="bg-slate-50 text-xs text-slate-600 dark:bg-white/5 dark:text-slate-300">
							<tr>
								<th class="px-4 py-3 text-left">Ders</th>
								<th class="px-4 py-3 text-center">Vize</th>
								<th class="px-4 py-3 text-center">Final</th>
								<th class="px-4 py-3 text-center">Harf</th>
								<th class="px-4 py-3 text-center">Durum</th>
							</tr>
						</thead>
						<tbody>
							{#each prepGrades as g}
								<tr class="border-t border-black/5 dark:border-white/10">
									<td class="px-4 py-3">
										<div class="font-mono text-xs font-semibold">{g.course_code}</div>
										<div class="text-xs text-slate-500">{g.course_name}</div>
									</td>
									<td class="px-4 py-3 text-center">{g.midterm ?? '—'}</td>
									<td class="px-4 py-3 text-center">{g.final ?? '—'}</td>
									<td class="px-4 py-3 text-center font-semibold">
										{#if g.is_published && g.letter_grade}
											<span class="rounded-full bg-emerald-100 px-2.5 py-0.5 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">{g.letter_grade}</span>
										{:else}—{/if}
									</td>
									<td class="px-4 py-3 text-center text-xs">
										{#if g.is_published}<span class="text-emerald-600">Yayınlandı</span>
										{:else}<span class="text-slate-400">Bekleniyor</span>{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>

		<!-- ============================================================ -->
		<!-- HAZIRLIK — DEVAMSIZLIK                                       -->
		<!-- ============================================================ -->
		{:else if apiKey === 'prep-attendance'}
			<div class="overflow-hidden rounded-2xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead class="bg-slate-50 text-xs text-slate-600 dark:bg-white/5 dark:text-slate-300">
							<tr>
								<th class="px-4 py-3 text-left">Ders</th>
								<th class="px-4 py-3 text-center">Toplam Hafta</th>
								<th class="px-4 py-3 text-center">Devamsız</th>
								<th class="px-4 py-3 text-center">Devam %</th>
								<th class="px-4 py-3 text-center">Durum</th>
							</tr>
						</thead>
						<tbody>
							{#each prepAttendance as a}
								<tr class="border-t border-black/5 dark:border-white/10">
									<td class="px-4 py-3">
										<div class="font-mono text-xs font-semibold">{a.course_code}</div>
										<div class="text-xs text-slate-500">{a.course_name}</div>
									</td>
									<td class="px-4 py-3 text-center">{a.total_weeks}</td>
									<td class="px-4 py-3 text-center">{a.absent_count}</td>
									<td class="px-4 py-3 text-center font-semibold">%{a.attendance_pct.toFixed(1)}</td>
									<td class="px-4 py-3 text-center">
										<span class="rounded-full px-2.5 py-0.5 text-xs {a.status === 'ok' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' : a.status === 'warning' ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300' : 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'}">
											{a.status === 'ok' ? 'İyi' : a.status === 'warning' ? 'Uyarı' : 'Kritik'}
										</span>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>

		<!-- ============================================================ -->
		<!-- ŞİFRE DEĞİŞTİR                                              -->
		<!-- ============================================================ -->
		{:else if apiKey === 'change-password'}
			<div class="mx-auto max-w-md rounded-2xl border border-black/10 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="mb-5 text-sm font-semibold">Şifre Değiştir</div>
				{#if pwSuccess}
					<div class="mb-4 rounded-lg bg-emerald-50 px-3 py-2.5 text-sm text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200">{pwSuccess}</div>
				{/if}
				{#if pwError}
					<div class="mb-4 rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-200">{pwError}</div>
				{/if}
				<div class="space-y-4">
					{#each [['Mevcut Şifre','current_password'], ['Yeni Şifre','new_password'], ['Yeni Şifre (Tekrar)','new_password_confirm']] as [lbl, field]}
						<label class="block">
							<div class="text-xs font-semibold text-slate-500">{lbl}</div>
							<input bind:value={pwForm[field as keyof typeof pwForm]} type="password" class="mt-1 w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-white/5" autocomplete="current-password" />
						</label>
					{/each}
					<button on:click={submitPassword} disabled={pwSubmitting} type="button" class="w-full rounded-xl bg-sky-500 py-2 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50">
						{pwSubmitting ? 'Değiştiriliyor…' : 'Şifreyi Güncelle'}
					</button>
				</div>
				<p class="mt-4 text-xs text-slate-400">Şifre en az 8 karakter uzunluğunda olmalıdır.</p>
			</div>

		<!-- ============================================================ -->
		<!-- FOTOĞRAF GÜNCELLE                                            -->
		<!-- ============================================================ -->
		{:else if apiKey === 'photo-update'}
			<div class="mx-auto max-w-md rounded-2xl border border-black/10 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="mb-5 text-sm font-semibold">Fotoğraf Güncelle</div>
				<div class="flex flex-col items-center gap-4">
					<div class="flex h-24 w-24 items-center justify-center rounded-full bg-sky-100 text-4xl font-bold text-sky-600 dark:bg-sky-900/40 dark:text-sky-300">
						{($user?.name ?? 'Ö').charAt(0).toUpperCase()}
					</div>
					<label class="cursor-pointer rounded-xl border border-black/10 px-4 py-2 text-sm font-medium hover:bg-slate-50 dark:border-white/10 dark:hover:bg-white/5">
						Dosya Seç
						<input type="file" accept="image/*" class="hidden" />
					</label>
					<p class="text-center text-xs text-slate-400">JPG, PNG veya GIF — maks. 2 MB<br>(Bu sayfa mock modda — yükleme simüle edilir)</p>
				</div>
			</div>

		<!-- ============================================================ -->
		<!-- VARSAYILAN (api yok veya bilinmiyor)                          -->
		<!-- ============================================================ -->
		{:else}
			<div class="rounded-2xl border border-dashed border-slate-200 bg-slate-50/80 p-6 dark:border-white/10 dark:bg-white/5">
				<div class="flex items-center gap-3">
					<span class="rounded-full bg-slate-200 px-2.5 py-1 text-xs font-semibold text-slate-600 dark:bg-white/10 dark:text-slate-300">
						Geliştirme aşamasında
					</span>
				</div>
				<div class="mt-3 text-sm font-medium text-slate-700 dark:text-slate-200">{pageTitle}</div>
				<p class="mt-1 text-sm text-slate-500 dark:text-slate-400">
					Bu sayfanın backend bağlantısı henüz eklenmedi. Yol haritasındaki Faz 3–4 kapsamında geliştirilecek.
				</p>
				<div class="mt-4 rounded-xl border border-slate-200 bg-white px-4 py-3 dark:border-white/10 dark:bg-white/5">
					<div class="text-xs font-semibold text-slate-500 dark:text-slate-400">Planlanan endpoint</div>
					<code class="mt-1 block text-xs text-slate-600 dark:text-slate-300">{hint}</code>
				</div>
			</div>
		{/if}

		<!-- Mock uyarısı -->
		{#if apiKey && !loading && !loadErr}
			<div class="rounded-xl border border-amber-200/60 bg-amber-50/60 px-3 py-2 text-xs text-amber-700 dark:border-amber-900/30 dark:bg-amber-950/20 dark:text-amber-300">
				Mock veri — PostgreSQL migration'ları tamamlandığında gerçek verilerle değiştirilecek.
			</div>
		{/if}
	</div>
</ObsShell>
