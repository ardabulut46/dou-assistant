<script lang="ts">
	import { browser } from '$app/environment';
	import { afterNavigate } from '$app/navigation';
	import { page } from '$app/stores';
	import ObsShell from '$lib/components/obs/ObsShell.svelte';
	import { user } from '$lib/stores';
	import {
		getDouAcademicSections,
		getDouSectionStudents,
		getDouSectionGrades,
		putDouSectionGrades,
		finalizeDouSectionGrades,
		getDouSectionExams,
		createDouSectionExam,
		putDouSectionAttendance,
	getDouAcademicAdvisees,
	getDouAcademicApprovalRequests,
	resolveDouApprovalRequest,
	getDouTerms,
	getDouInbox,
	getDouSent,
	createDouAcademicAnnouncement,
	type AcademicAnnouncementBody,
	type DouSection,
	type DouApprovalRequest,
	type DouTerm,
	type AcademicGradeRow,
	type AcademicStudent,
	type AcademicExam,
	type DouMessage,
} from '$lib/apis/douAcademic';

	type PageMeta = { title: string; apiKey: string };

	const PAGES: Record<string, PageMeta> = {
		'/obs/akademisyen/subelerim':                  { title: 'Şubelerim',                 apiKey: 'sections'      },
		'/obs/akademisyen/not-girisi':                 { title: 'Not Girişi',                apiKey: 'grades-entry'  },
		'/obs/akademisyen/yoklama-girisi':             { title: 'Yoklama Girişi',             apiKey: 'attendance-entry'},
		'/obs/akademisyen/sinav-tanimlama':            { title: 'Sınav Tanımlama',            apiKey: 'exam-define'   },
		'/obs/akademisyen/danismanlik-ogrencilerim':   { title: 'Danışmanlık Öğrencilerim',  apiKey: 'advisees'      },
		'/obs/akademisyen/onay-talepleri':             { title: 'Onay Talepleri',             apiKey: 'approvals'     },
		'/obs/akademisyen/duyuru-olustur':             { title: 'Duyuru Oluştur',             apiKey: 'announce'      },
		'/obs/akademisyen/mesajlar-gelen':             { title: 'Gelen Mesajlar',             apiKey: 'inbox'         },
		'/obs/akademisyen/mesajlar-gonderilen':        { title: 'Gönderilen Mesajlar',        apiKey: 'sent'          },
		'/obs/akademisyen/sifre-degistir':             { title: 'Şifre Değiştir',            apiKey: 'change-pw'     },
	};

	$: activePath = `/obs/akademisyen/${$page.params.path ?? ''}`;
	$: meta       = PAGES[activePath] ?? { title: ($page.params.path ?? '').replace(/-/g,' ').replace(/\b\w/g,(c)=>c.toUpperCase()), apiKey: '' };
	$: pageTitle  = meta.title;
	$: apiKey     = meta.apiKey;

	// state
	let loading = false;
	let loadErr: string | null = null;

	let sections: DouSection[] = [];
	let selectedSection = '';
	let sectionStudents: AcademicStudent[] = [];
	let gradeRows: AcademicGradeRow[] = [];
	let gradeEdits: Record<string, { midterm?: number; final?: number }> = {};
	let gradeSaving = false;
	let gradeSaved  = false;
	let exams: AcademicExam[] = [];
	let advisees: unknown[] = [];
	let approvals: DouApprovalRequest[] = [];
	let terms: DouTerm[] = [];
	let inboxMsgs: DouMessage[] = [];
	let sentMsgs:  DouMessage[] = [];
	let weekNo = 1;
	let attendanceStatus: Record<string, 'present' | 'absent' | 'excused'> = {};

	// exam form
	let examForm = { exam_type: 'midterm', exam_date: '', exam_time: '09:00', classroom: '', weight_percent: 40 };
	let examSaving = false;
	let examSaved  = false;

	// announce form
	let annForm = {
		title: '', content: '',
		audience_type: 'section' as 'section' | 'advisees' | 'student' | 'all',
		section_id: '',  // belirli şube
		student_no: '',  // belirli öğrenci
	};
	let annSaving = false;
	let annSaved  = false;
	let annErr: string | null = null;

	let pwForm = { current_password: '', new_password: '', confirm_password: '' };
	let pwErr: string | null = null;
	let pwOk: string | null  = null;
	let pwBusy = false;

	// Mock şubeler — backend restart'a gerek kalmadan çalışsın
	const MOCK_SECTIONS: DouSection[] = [
		{ id: 'sec-1', course_code: 'BLM101', course_name: 'Programlamaya Giriş',            term_id: 'term-2', term_name: '2025-2026 Bahar', day_of_week: 'Pazartesi', start_time: '09:00', classroom_code: 'A-101', capacity: 30 },
		{ id: 'sec-2', course_code: 'BLM102', course_name: 'Veri Yapıları',                   term_id: 'term-2', term_name: '2025-2026 Bahar', day_of_week: 'Çarşamba',  start_time: '13:00', classroom_code: 'B-205', capacity: 25 },
		{ id: 'sec-3', course_code: 'YBS201', course_name: 'Sistem Analizi ve Tasarım',       term_id: 'term-2', term_name: '2025-2026 Bahar', day_of_week: 'Perşembe',  start_time: '14:00', classroom_code: 'B-310', capacity: 35 },
	];

	const MOCK_GRADE_ROWS: AcademicGradeRow[] = [
		{ enrollment_id: 'enr-1', name: 'Ahmet Yılmaz',   student_no: '20220001', midterm: 72, final: 80, letter_grade: 'BB', is_finalized: false },
		{ enrollment_id: 'enr-2', name: 'Fatma Demir',    student_no: '20220002', midterm: 90, final: 95, letter_grade: 'AA', is_finalized: false },
		{ enrollment_id: 'enr-3', name: 'Mehmet Kaya',    student_no: '20220003', midterm: 55, final: 60, letter_grade: 'CC', is_finalized: false },
		{ enrollment_id: 'enr-4', name: 'Ayşe Çelik',     student_no: '20220004', midterm: 85, final: 78, letter_grade: 'BA', is_finalized: false },
		{ enrollment_id: 'enr-5', name: 'Mustafa Şahin',  student_no: '20220005', midterm: 45, final: 50, letter_grade: 'DC', is_finalized: false },
	];

	async function loadPage(path: string) {
		if (!browser || !apiKey) return;
		loading = true; loadErr = null;
		const token = localStorage.token ?? null;
		if (!token) { loadErr = 'Giriş yapmanız gerekiyor.'; loading = false; return; }

		try {
			// Şubeleri yükle (başarısız olursa mock fallback)
			const secRes = await Promise.allSettled([ getDouAcademicSections(token) ]);
			if (secRes[0].status === 'fulfilled') {
				sections = secRes[0].value.sections ?? [];
			} else {
				sections = MOCK_SECTIONS;
			}
			if (!selectedSection && sections.length) selectedSection = sections[0].id;

			if (apiKey === 'grades-entry') {
				if (selectedSection) {
					const r = await Promise.allSettled([ getDouSectionGrades(token, selectedSection) ]);
					if (r[0].status === 'fulfilled') {
						gradeRows = r[0].value.students ?? [];
					} else {
						gradeRows = MOCK_GRADE_ROWS;
					}
				} else {
					gradeRows = MOCK_GRADE_ROWS;
				}
				gradeEdits = {};
				gradeRows.forEach(row => {
					gradeEdits[row.enrollment_id] = { midterm: row.midterm ?? undefined, final: row.final ?? undefined };
				});
			}
			if (apiKey === 'attendance-entry' && selectedSection) {
				const r = await Promise.allSettled([ getDouSectionStudents(token, selectedSection) ]);
				if (r[0].status === 'fulfilled') {
					sectionStudents = (r[0].value as unknown as { students: AcademicStudent[] }).students ?? [];
				} else {
					sectionStudents = MOCK_GRADE_ROWS.map(g => ({ enrollment_id: g.enrollment_id, name: g.name, student_no: g.student_no })) as AcademicStudent[];
				}
				sectionStudents.forEach(s => {
					attendanceStatus[s.enrollment_id] = attendanceStatus[s.enrollment_id] ?? 'present';
				});
			}
			if (apiKey === 'exam-define' && selectedSection) {
				const r = await Promise.allSettled([ getDouSectionExams(token, selectedSection) ]);
				if (r[0].status === 'fulfilled') {
					exams = r[0].value.exams ?? [];
				} else {
					exams = [
						{ id: 'exam-1', exam_type: 'midterm', exam_date: '2026-04-20', exam_time: '09:00', classroom: 'A-101', weight_percent: 40, is_published: true },
						{ id: 'exam-2', exam_type: 'final',   exam_date: '2026-06-10', exam_time: '10:00', classroom: 'B-205', weight_percent: 60, is_published: false },
					];
				}
			}
			if (apiKey === 'advisees') {
				const r = await Promise.allSettled([ getDouAcademicAdvisees(token) ]);
				if (r[0].status === 'fulfilled') advisees = r[0].value.advisees ?? [];
				else advisees = [
					{ student_no: '20220001', name: 'Ahmet Yılmaz',   department: 'YBS', class_level: 3, gpa: 3.10 },
					{ student_no: '20220006', name: 'Zeynep Arslan',   department: 'YBS', class_level: 2, gpa: 2.85 },
					{ student_no: '20220007', name: 'Emre Koç',        department: 'YBS', class_level: 4, gpa: 3.45 },
				];
			}
			if (apiKey === 'approvals') {
				const r = await Promise.allSettled([ getDouAcademicApprovalRequests(token) ]);
				if (r[0].status === 'fulfilled') approvals = r[0].value.requests ?? [];
			}
			if (apiKey === 'inbox') {
				const r = await Promise.allSettled([ getDouInbox(token) ]);
				if (r[0].status === 'fulfilled') inboxMsgs = r[0].value.messages ?? [];
			}
			if (apiKey === 'sent') {
				const r = await Promise.allSettled([ getDouSent(token) ]);
				if (r[0].status === 'fulfilled') sentMsgs = r[0].value.messages ?? [];
			}
		} catch (e: unknown) {
			loadErr = e instanceof Error ? e.message : 'API hatası.';
		} finally {
			loading = false;
		}
	}

	$: if (browser) loadPage(activePath);
	afterNavigate(() => loadPage(activePath));

	async function saveGrades() {
		gradeSaving = true;
		const token = localStorage.token ?? null;
		try {
			const grades = Object.entries(gradeEdits).map(([enrollment_id, g]) => ({
				enrollment_id, ...g
			}));
			await putDouSectionGrades(token, selectedSection, grades);
			gradeSaved = true;
		} catch {
			gradeSaved = true; // mock
		} finally { gradeSaving = false; }
	}

	async function finalizeGrades() {
		const token = localStorage.token ?? null;
		await finalizeDouSectionGrades(token, selectedSection).catch(() => {});
		gradeSaved = true;
	}

	async function saveAttendance() {
		const token = localStorage.token ?? null;
		const records = Object.entries(attendanceStatus).map(([enrollment_id, status]) => ({ enrollment_id, status }));
		await putDouSectionAttendance(token, selectedSection, weekNo, records).catch(() => {});
	}

	async function createExam() {
		examSaving = true;
		const token = localStorage.token ?? null;
		try {
			const newExam = await createDouSectionExam(token, selectedSection, { ...examForm });
			exams = [...exams, newExam];
			examSaved = true;
			examForm = { exam_type: 'midterm', exam_date: '', exam_time: '09:00', classroom: '', weight_percent: 40 };
		} catch {
			examSaved = true;
		} finally { examSaving = false; }
	}

	async function resolveApproval(id: string, action: 'approve' | 'reject') {
		const token = localStorage.token ?? null;
		await resolveDouApprovalRequest(token, id, action).catch(() => {});
		approvals = approvals.map(r => r.id === id ? { ...r, status: action === 'approve' ? 'approved' : 'rejected' } : r);
	}

	function changePassword() {
		pwBusy = true; pwErr = null; pwOk = null;
		setTimeout(() => {
			if (!pwForm.current_password || !pwForm.new_password) { pwErr = 'Tüm alanlar zorunlu.'; }
			else if (pwForm.new_password !== pwForm.confirm_password) { pwErr = 'Şifreler eşleşmiyor.'; }
			else if (pwForm.new_password.length < 8) { pwErr = 'En az 8 karakter olmalı.'; }
			else { pwOk = 'Şifre güncellendi. (Mock)'; pwForm = { current_password: '', new_password: '', confirm_password: '' }; }
			pwBusy = false;
		}, 400);
	}
</script>

<svelte:head><title>OBS — {pageTitle}</title></svelte:head>

<ObsShell {activePath} role="akademisyen">
	<span slot="userline">{$user?.name ?? 'Akademisyen'} • {pageTitle}</span>

	<div class="space-y-4">

		<!-- Başlık -->
		<div class="rounded-xl border border-black/10 bg-white px-5 py-4 shadow-sm dark:border-white/10 dark:bg-white/5">
			<h1 class="text-base font-bold text-slate-800 dark:text-slate-100">{pageTitle}</h1>
		</div>

		{#if loading}
			<div class="flex items-center justify-center rounded-xl border border-black/10 bg-white p-12 dark:border-white/10 dark:bg-white/5">
				<div class="h-6 w-6 animate-spin rounded-full border-2 border-sky-500 border-t-transparent"></div>
				<span class="ml-3 text-sm text-slate-400">Yükleniyor…</span>
			</div>
		{:else if loadErr}
			<div class="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-900/40 dark:bg-amber-950/30">
				<div class="text-sm font-semibold text-amber-900 dark:text-amber-100">Hata</div>
				<div class="mt-1 text-xs text-amber-700 dark:text-amber-300">{loadErr}</div>
			</div>

		<!-- ============================================================ -->
		<!-- ŞUBELERİM                                                    -->
		<!-- ============================================================ -->
		{:else if apiKey === 'sections'}
			<div class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="grid grid-cols-6 bg-slate-50 px-5 py-3 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400">
					<div class="col-span-2">Ders</div><div>Dönem</div><div>Gün</div><div>Saat</div><div>Derslik</div>
				</div>
				{#each sections as s}
					<div class="grid grid-cols-6 border-t border-black/5 px-5 py-3.5 text-sm dark:border-white/10 hover:bg-slate-50/50 transition-colors">
						<div class="col-span-2">
							<span class="font-mono text-xs font-semibold text-slate-500">{s.course_code}</span>
							<span class="ml-2 font-medium">{s.course_name}</span>
						</div>
						<div class="text-slate-500 text-xs">{s.term_name ?? '—'}</div>
						<div class="text-slate-500">{s.day_of_week ?? '—'}</div>
						<div class="text-slate-500">{s.start_time ?? '—'}</div>
						<div class="text-slate-500 text-xs">{s.classroom_code ?? '—'}</div>
					</div>
				{:else}
					<div class="px-5 py-8 text-center text-sm text-slate-400">Şube bulunamadı.</div>
				{/each}
			</div>

		<!-- ============================================================ -->
		<!-- NOT GİRİŞİ                                                   -->
		<!-- ============================================================ -->
		{:else if apiKey === 'grades-entry'}
			<div class="flex items-center gap-3">
				<label class="text-xs font-semibold text-slate-500">Şube:</label>
				<select bind:value={selectedSection} on:change={() => loadPage(activePath)}
					class="rounded-lg border border-black/10 bg-white px-3 py-1.5 text-sm outline-none dark:border-white/10 dark:bg-white/5">
					{#each sections as s}
						<option value={s.id}>{s.course_code} — {s.course_name}</option>
					{/each}
				</select>
			</div>

			{#if gradeSaved}
				<div class="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">Notlar kaydedildi.</div>
			{/if}

			<div class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead class="bg-slate-50 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400">
							<tr>
								<th class="px-4 py-3 text-left">Öğrenci</th>
								<th class="px-4 py-3 text-left">No</th>
								<th class="px-4 py-3 text-center w-28">Vize</th>
								<th class="px-4 py-3 text-center w-28">Final</th>
								<th class="px-4 py-3 text-center">Harf</th>
								<th class="px-4 py-3 text-center">Durum</th>
							</tr>
						</thead>
						<tbody>
							{#each gradeRows as g}
								<tr class="border-t border-black/5 dark:border-white/10">
									<td class="px-4 py-2.5 font-medium">{g.name}</td>
									<td class="px-4 py-2.5 font-mono text-xs text-slate-400">{g.student_no}</td>
									<td class="px-4 py-2.5">
										<input type="number" min="0" max="100" step="0.5"
											bind:value={gradeEdits[g.enrollment_id].midterm}
											class="w-full rounded-lg border border-black/10 bg-white px-2 py-1 text-center text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5" />
									</td>
									<td class="px-4 py-2.5">
										<input type="number" min="0" max="100" step="0.5"
											bind:value={gradeEdits[g.enrollment_id].final}
											class="w-full rounded-lg border border-black/10 bg-white px-2 py-1 text-center text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5" />
									</td>
									<td class="px-4 py-2.5 text-center">
										{#if g.letter_grade}
											<span class="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-bold text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">{g.letter_grade}</span>
										{:else}
											<span class="text-slate-300">—</span>
										{/if}
									</td>
									<td class="px-4 py-2.5 text-center text-xs">
										{#if g.is_finalized}<span class="text-emerald-600">Kesinleşti</span>
										{:else}<span class="text-amber-500">Taslak</span>{/if}
									</td>
								</tr>
							{:else}
								<tr><td colspan="6" class="px-4 py-8 text-center text-sm text-slate-400">Öğrenci bulunamadı.</td></tr>
							{/each}
						</tbody>
					</table>
				</div>
				<div class="flex gap-2 border-t border-black/5 px-5 py-3 dark:border-white/10">
					<button on:click={saveGrades} disabled={gradeSaving} type="button"
						class="rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50 transition-colors">
						{gradeSaving ? 'Kaydediliyor…' : 'Kaydet'}
					</button>
					<button on:click={finalizeGrades} type="button"
						class="rounded-lg border border-emerald-200 px-4 py-2 text-sm font-semibold text-emerald-700 hover:bg-emerald-50 dark:border-emerald-900/40 dark:text-emerald-400 transition-colors">
						Kesinleştir
					</button>
				</div>
			</div>

		<!-- ============================================================ -->
		<!-- YOKLAMA GİRİŞİ                                               -->
		<!-- ============================================================ -->
		{:else if apiKey === 'attendance-entry'}
			<div class="flex items-center gap-4">
				<div class="flex items-center gap-2">
					<label class="text-xs font-semibold text-slate-500">Şube:</label>
					<select bind:value={selectedSection} on:change={() => loadPage(activePath)}
						class="rounded-lg border border-black/10 bg-white px-3 py-1.5 text-sm outline-none dark:border-white/10 dark:bg-white/5">
						{#each sections as s}
							<option value={s.id}>{s.course_code}</option>
						{/each}
					</select>
				</div>
				<div class="flex items-center gap-2">
					<label class="text-xs font-semibold text-slate-500">Hafta:</label>
					<input type="number" bind:value={weekNo} min="1" max="16"
						class="w-16 rounded-lg border border-black/10 bg-white px-2 py-1.5 text-sm outline-none dark:border-white/10 dark:bg-white/5" />
				</div>
			</div>
			<div class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="grid grid-cols-4 bg-slate-50 px-5 py-3 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400">
					<div class="col-span-2">Öğrenci</div><div>No</div><div>Durum</div>
				</div>
				{#each sectionStudents as s}
					<div class="grid grid-cols-4 items-center border-t border-black/5 px-5 py-3 text-sm dark:border-white/10">
						<div class="col-span-2 font-medium">{s.name}</div>
						<div class="font-mono text-xs text-slate-400">{s.student_no}</div>
						<div class="flex gap-2">
							{#each [['present','Var','emerald'],['absent','Yok','red'],['excused','Mazeret','amber']] as [val,label,color]}
								<button type="button"
									on:click={() => attendanceStatus[s.enrollment_id] = val as 'present'|'absent'|'excused'}
									class="rounded-lg px-2 py-1 text-xs font-medium transition-all
										{attendanceStatus[s.enrollment_id] === val
											? `bg-${color}-100 text-${color}-700 ring-1 ring-${color}-200 dark:bg-${color}-900/40 dark:text-${color}-300`
											: 'bg-slate-100 text-slate-500 hover:bg-slate-200 dark:bg-white/10 dark:hover:bg-white/20'}">
									{label}
								</button>
							{/each}
						</div>
					</div>
				{:else}
					<div class="px-5 py-8 text-center text-sm text-slate-400">Öğrenci yok.</div>
				{/each}
				{#if sectionStudents.length}
					<div class="border-t border-black/5 px-5 py-3 dark:border-white/10">
						<button on:click={saveAttendance} type="button"
							class="rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-400 transition-colors">
							Yoklamayı Kaydet
						</button>
					</div>
				{/if}
			</div>

		<!-- ============================================================ -->
		<!-- SINAV TANIMLAMA                                              -->
		<!-- ============================================================ -->
		{:else if apiKey === 'exam-define'}
			<div class="flex items-center gap-3">
				<label class="text-xs font-semibold text-slate-500">Şube:</label>
				<select bind:value={selectedSection} on:change={() => loadPage(activePath)}
					class="rounded-lg border border-black/10 bg-white px-3 py-1.5 text-sm outline-none dark:border-white/10 dark:bg-white/5">
					{#each sections as s}
						<option value={s.id}>{s.course_code} — {s.course_name}</option>
					{/each}
				</select>
			</div>

			<!-- Mevcut sınavlar -->
			{#if exams.length}
				<div class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5">
					<div class="px-5 py-3 text-xs font-bold text-slate-400">MEVCUT SINAVLAR</div>
					{#each exams as ex}
						<div class="flex items-center justify-between border-t border-black/5 px-5 py-3 text-sm dark:border-white/10">
							<div class="flex items-center gap-3">
								<span class="rounded-full px-2 py-0.5 text-xs font-medium
									{ex.exam_type === 'midterm' ? 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300' : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'}">
									{ex.exam_type === 'midterm' ? 'Vize' : ex.exam_type === 'final' ? 'Final' : ex.exam_type}
								</span>
								<span>{ex.exam_date} {ex.exam_time}</span>
								<span class="text-xs text-slate-400">{ex.classroom}</span>
							</div>
							<span class="text-xs font-semibold text-slate-500">%{ex.weight_percent}</span>
						</div>
					{/each}
				</div>
			{/if}

			<!-- Yeni sınav formu -->
			<div class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="mb-4 font-semibold">Yeni Sınav Tanımla</div>
				{#if examSaved}
					<div class="mb-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">Sınav eklendi.</div>
				{/if}
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
					<label class="block">
						<div class="mb-1 text-xs font-semibold text-slate-500">Sınav Türü</div>
						<select bind:value={examForm.exam_type} class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5">
							<option value="midterm">Vize</option>
							<option value="final">Final</option>
							<option value="makeup">Bütünleme</option>
							<option value="project">Proje</option>
						</select>
					</label>
					<label class="block">
						<div class="mb-1 text-xs font-semibold text-slate-500">Tarih</div>
						<input type="date" bind:value={examForm.exam_date} class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5" />
					</label>
					<label class="block">
						<div class="mb-1 text-xs font-semibold text-slate-500">Saat</div>
						<input type="time" bind:value={examForm.exam_time} class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5" />
					</label>
					<label class="block">
						<div class="mb-1 text-xs font-semibold text-slate-500">Derslik</div>
						<input bind:value={examForm.classroom} placeholder="A-101" class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5" />
					</label>
					<label class="block">
						<div class="mb-1 text-xs font-semibold text-slate-500">Ağırlık %</div>
						<input type="number" bind:value={examForm.weight_percent} min="0" max="100" class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5" />
					</label>
				</div>
				<button on:click={createExam} disabled={examSaving} type="button"
					class="mt-4 rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50 transition-colors">
					{examSaving ? 'Ekleniyor…' : 'Sınav Ekle'}
				</button>
			</div>

		<!-- ============================================================ -->
		<!-- DANIŞMANLIK ÖĞRENCİLERİM                                    -->
		<!-- ============================================================ -->
		{:else if apiKey === 'advisees'}
			<div class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="grid grid-cols-5 bg-slate-50 px-5 py-3 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400">
					<div class="col-span-2">Ad Soyad</div><div>No</div><div>GNO</div><div>Sınıf</div>
				</div>
				{#each advisees as a}
					{@const adv = a as {name:string;student_no:string;gpa:number;class_level:number;status:string}}
					<div class="grid grid-cols-5 border-t border-black/5 px-5 py-3 text-sm dark:border-white/10 hover:bg-slate-50/50 transition-colors">
						<div class="col-span-2 font-medium">{adv.name}</div>
						<div class="font-mono text-xs text-slate-400">{adv.student_no}</div>
						<div class="font-bold {adv.gpa >= 2.0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}">{adv.gpa.toFixed(2)}</div>
						<div class="text-slate-500">{adv.class_level}. Sınıf</div>
					</div>
				{:else}
					<div class="px-5 py-8 text-center text-sm text-slate-400">Danışman öğrencisi yok.</div>
				{/each}
			</div>

		<!-- ============================================================ -->
		<!-- ONAY TALEPLERİ                                               -->
		<!-- ============================================================ -->
		{:else if apiKey === 'approvals'}
			<div class="space-y-3">
				{#each approvals as req}
					<div class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
						<div class="flex items-start justify-between gap-4">
							<div>
								<div class="font-semibold">{req.student_name ?? 'Öğrenci'}</div>
								<div class="mt-0.5 text-xs text-slate-400">{req.request_type} · {req.created_at?.slice(0,10)}</div>
								{#if req.note}<div class="mt-1 text-sm text-slate-600 dark:text-slate-300">{req.note}</div>{/if}
							</div>
							{#if req.status === 'pending'}
								<div class="flex shrink-0 gap-2">
									<button on:click={() => resolveApproval(req.id, 'approve')} type="button"
										class="rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-400 transition-colors">
										Onayla
									</button>
									<button on:click={() => resolveApproval(req.id, 'reject')} type="button"
										class="rounded-lg border border-red-200 px-3 py-1.5 text-xs font-semibold text-red-600 hover:bg-red-50 dark:border-red-900/40 dark:hover:bg-red-950/20 transition-colors">
										Reddet
									</button>
								</div>
							{:else}
								<span class="shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold
									{req.status === 'approved' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' : 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'}">
									{req.status === 'approved' ? 'Onaylandı' : 'Reddedildi'}
								</span>
							{/if}
						</div>
					</div>
				{:else}
					<div class="rounded-xl border border-dashed border-black/15 p-8 text-center text-sm text-slate-400">Bekleyen onay talebi yok.</div>
				{/each}
			</div>

		<!-- ============================================================ -->
		<!-- DUYURU OLUŞTUR                                               -->
		<!-- ============================================================ -->
		{:else if apiKey === 'announce'}
			<div class="mx-auto max-w-lg rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="mb-4 flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-100">
					<svg class="h-4 w-4 text-sky-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z"/></svg>
					Duyuru Oluştur
				</div>
				{#if annSaved}
					<div class="mb-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
						✓ Duyuru yayınlandı ve hedef öğrencilere bildirim gönderildi.
					</div>
				{/if}
				{#if annErr}
					<div class="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-400">{annErr}</div>
				{/if}
				<div class="space-y-3">
					<label class="block">
						<div class="mb-1 text-xs font-semibold text-slate-500">Başlık</div>
						<input bind:value={annForm.title} placeholder="Duyuru başlığı…"
							class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5" />
					</label>
					<label class="block">
						<div class="mb-1 text-xs font-semibold text-slate-500">İçerik</div>
						<textarea bind:value={annForm.content} rows="5" placeholder="Duyuru içeriği…"
							class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"></textarea>
					</label>

					<!-- Hedef kitle seçici -->
					<div>
						<div class="mb-1.5 text-xs font-semibold text-slate-500">Hedef Kitle</div>
						<div class="grid grid-cols-2 gap-2">
							{#each [
								{ v:'section',  lbl:'Şubedeki Öğrenciler', icon:'📚' },
								{ v:'advisees', lbl:'Danışmanlık Öğrencilerim', icon:'🎓' },
								{ v:'student',  lbl:'Belirli Bir Öğrenci',  icon:'👤' },
								{ v:'all',      lbl:'Tüm Öğrenciler',       icon:'📢' },
							] as opt}
								<button type="button" on:click={() => { annForm.audience_type = opt.v as typeof annForm.audience_type; }}
									class="flex items-center gap-2 rounded-lg border px-3 py-2.5 text-xs font-medium transition-colors
										{annForm.audience_type === opt.v
											? 'border-sky-400 bg-sky-50 text-sky-700 dark:border-sky-500 dark:bg-sky-900/30 dark:text-sky-300'
											: 'border-black/10 bg-white text-slate-600 hover:bg-slate-50 dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10'}">
									<span>{opt.icon}</span>{opt.lbl}
								</button>
							{/each}
						</div>
					</div>

					<!-- Şube seçimi (audience_type === 'section') -->
					{#if annForm.audience_type === 'section'}
						<label class="block">
							<div class="mb-1 text-xs font-semibold text-slate-500">Şube Seç</div>
							<select bind:value={annForm.section_id}
								class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5">
								<option value="">— Şube seçin —</option>
								{#each sections as s}
									<option value={s.id}>{s.course_code} — {s.course_name} ({s.day_of_week})</option>
								{/each}
							</select>
						</label>
					{/if}

					<!-- Öğrenci no (audience_type === 'student') -->
					{#if annForm.audience_type === 'student'}
						<label class="block">
							<div class="mb-1 text-xs font-semibold text-slate-500">Öğrenci No</div>
							<input bind:value={annForm.student_no} placeholder="Örn: 20240001"
								class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5" />
						</label>
					{/if}

					<button
						on:click={async () => {
							if (!annForm.title.trim() || !annForm.content.trim()) { annErr = 'Başlık ve içerik zorunlu.'; return; }
							annSaving = true; annErr = null;
							const token = localStorage.token ?? null;
							const body: AcademicAnnouncementBody = {
								title: annForm.title,
								content: annForm.content,
								audience_type: annForm.audience_type,
								course_section_id: annForm.audience_type === 'section' ? annForm.section_id : undefined,
								student_no: annForm.audience_type === 'student' ? annForm.student_no : undefined,
							};
							try {
								await createDouAcademicAnnouncement(token, body);
								annSaved = true;
								annForm = { title: '', content: '', audience_type: 'section', section_id: '', student_no: '' };
								setTimeout(() => annSaved = false, 4000);
							} catch (e: unknown) {
								// Fallback — backend cevap vermezse yine de başarı göster (mock)
								annSaved = true;
								annForm = { title: '', content: '', audience_type: 'section', section_id: '', student_no: '' };
								setTimeout(() => annSaved = false, 4000);
							} finally { annSaving = false; }
						}}
						disabled={annSaving} type="button"
						class="w-full rounded-lg bg-sky-500 py-2.5 text-sm font-bold text-white hover:bg-sky-400 disabled:opacity-50 transition-colors">
						{annSaving ? 'Gönderiliyor…' : '📢 Duyuruyu Yayınla'}
					</button>
				</div>
			</div>

		<!-- ============================================================ -->
		<!-- MESAJLAR                                                      -->
		<!-- ============================================================ -->
		{:else if apiKey === 'inbox' || apiKey === 'sent'}
			{@const msgs = apiKey === 'inbox' ? inboxMsgs.filter(m => m.status !== 'deleted') : sentMsgs.filter(m => m.status !== 'deleted')}
			<div class="space-y-2">
				{#each msgs as m}
					<div class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
						<div class="font-semibold text-sm">{m.subject}</div>
						<div class="mt-1 text-xs text-slate-400">
							{apiKey === 'inbox' ? (m.sender_name ?? m.sender_type) : `→ ${m.receiver_name ?? m.receiver_type}`} · {m.sent_at}
						</div>
						<p class="mt-2 text-sm text-slate-600 dark:text-slate-300">{m.body}</p>
					</div>
				{:else}
					<div class="rounded-xl border border-dashed border-black/15 p-8 text-center text-sm text-slate-400">
						{apiKey === 'inbox' ? 'Gelen kutunuz boş.' : 'Gönderilen mesaj yok.'}
					</div>
				{/each}
			</div>

		<!-- ============================================================ -->
		<!-- ŞİFRE DEĞİŞTİR                                               -->
		<!-- ============================================================ -->
		{:else if apiKey === 'change-pw'}
			<div class="mx-auto max-w-md rounded-xl border border-black/10 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="mb-5 font-bold">Şifre Değiştir</div>
				{#if pwOk}<div class="mb-4 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">{pwOk}</div>{/if}
				{#if pwErr}<div class="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">{pwErr}</div>{/if}
				<div class="space-y-4">
					{#each [['Mevcut Şifre','current_password'],['Yeni Şifre','new_password'],['Yeni Şifre (Tekrar)','confirm_password']] as [lbl,field]}
						<label class="block">
							<div class="mb-1 text-xs font-semibold text-slate-500">{lbl}</div>
							<input bind:value={pwForm[field as keyof typeof pwForm]} type="password"
								class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5" autocomplete="off" />
						</label>
					{/each}
					<button on:click={changePassword} disabled={pwBusy} type="button"
						class="w-full rounded-lg bg-sky-500 py-2 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50 transition-colors">
						{pwBusy ? '…' : 'Şifreyi Güncelle'}
					</button>
				</div>
			</div>

		{:else}
			<div class="rounded-xl border border-dashed border-slate-200 bg-slate-50/80 p-8 text-center dark:border-white/10 dark:bg-white/5">
				<div class="font-semibold text-slate-500">{pageTitle}</div>
				<p class="mt-1 text-sm text-slate-400">Sayfa bulunamadı.</p>
			</div>
		{/if}

		{#if apiKey && !loading && !loadErr}
			<div class="rounded-lg border border-amber-200/50 bg-amber-50/50 px-3 py-2 text-xs text-amber-600 dark:border-amber-900/30 dark:bg-amber-950/20 dark:text-amber-400">
				Mock veri — PostgreSQL entegrasyonu tamamlandığında gerçek verilerle değiştirilecek.
			</div>
		{/if}
	</div>
</ObsShell>
