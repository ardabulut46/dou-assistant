/** OBS öğrenci alt sayfa meta (URL → başlık + veri anahtarı) */
export const OGRENCI_PAGES = {
	'/obs/ogrenci/ozluk-bilgileri': { title: 'Özlük Bilgileri', apiKey: 'profile' },
	'/obs/ogrenci/akademik-takvim': { title: 'Akademik Takvim', apiKey: 'terms' },
	'/obs/ogrenci/danisman-bilgileri': { title: 'Danışman Bilgileri', apiKey: 'advisor' },
	'/obs/ogrenci/mufredat': { title: 'Müfredat Durumu', apiKey: 'curriculum' },
	'/obs/ogrenci/alinan-dersler': { title: 'Alınan Dersler', apiKey: 'enrollments' },
	'/obs/ogrenci/ders-programi': { title: 'Ders Programı', apiKey: 'schedule' },
	'/obs/ogrenci/sinav-takvimi': { title: 'Sınav Takvimi', apiKey: 'exams' },
	'/obs/ogrenci/ders-kayit': { title: 'Ders Kayıt', apiKey: 'ders-kayit' },
	'/obs/ogrenci/ders-ekle-birak': { title: 'Ders Ekle / Bırak', apiKey: 'ders-ekle' },
	'/obs/ogrenci/not-listesi': { title: 'Not Listesi', apiKey: 'grades' },
	'/obs/ogrenci/donem-ortalamalari': { title: 'Dönem Ortalamaları', apiKey: 'gpa' },
	'/obs/ogrenci/transkript': { title: 'Transkript', apiKey: 'transcript' },
	'/obs/ogrenci/devamsizlik-durumu': { title: 'Devamsızlık Durumu', apiKey: 'attendance' },
	'/obs/ogrenci/mesajlar-gelen': { title: 'Gelen Mesajlar', apiKey: 'inbox' },
	'/obs/ogrenci/mesajlar-gonderilen': { title: 'Gönderilen Mesajlar', apiKey: 'sent' },
	'/obs/ogrenci/belge-talebi': { title: 'Belge Talebi', apiKey: 'doc-request' },
	'/obs/ogrenci/duyurular': { title: 'Duyurular', apiKey: 'announcements' },
	'/obs/ogrenci/sifre-degistir': { title: 'Şifre Değiştir', apiKey: 'change-pw' }
} as const;

export type OgrenciPath = keyof typeof OGRENCI_PAGES;
export type OgrenciPageMeta = (typeof OGRENCI_PAGES)[OgrenciPath];

export function ogrenciLayoutSubtitle(pathname: string): string {
	if (pathname === '/obs/ogrenci' || pathname === '/obs/ogrenci/') {
		return 'Öğrenci Paneli';
	}
	if (pathname in OGRENCI_PAGES) {
		return OGRENCI_PAGES[pathname as OgrenciPath].title;
	}
	return 'OBS';
}
