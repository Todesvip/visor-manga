const recientesData = [
    {
        id: "Kaifuku",
        titulo: "Kaifuku Jutsushi no Yarinaoshi",
        titulo_jp: "回復術士のやり直し",
        poster: "https://static.zerochan.net/Kaifuku.Jutsushi.no.Yarinaoshi....1024.3112751.webp",
        banner: "",
        rating: "16+",
        temporada: "1 Temporada",
        ano: "2024",
        calidad: "HD",
        sinopsis: "Keyar es un sanador que es usado y despreciado por sus compañeros aventureros debido a que ellos piensan que los sanadores no pueden luchar por sí mismos. Cuando Keyar consigue el hechizo definitivo de sanación, el 'cura' al mundo, lo que le permite ir cuatro años en el pasado y vengarse de sus antiguos compañeros, cambiando su destino.",
        episodios: [
            { num: 1, nombre: "Episodio 1", duracion: "24m", thumb: "https://todesvip.github.io/visor-manga/thumb/Kaifuku Jutsushi no Yarinaoshi 01_thumb1.jpg", sprite: "https://todesvip.github.io/visor-manga/sprit/sprite.vtt", spriteImg: "https://todesvip.github.io/visor-manga/sprit/sprite.jpg", link: "https://ia601709.us.archive.org/29/items/seihou-shouka-saint-lime-1/Kaifuku%20Jutsushi%20no%20Yarinaoshi%2001.mkv", subtitulo: "https://todesvip.github.io/visor-manga/subtitles/Kaifuku Jutsushi no Yarinaoshi 01.spa.ass" },
            { num: 2, nombre: "Episodio 2", duracion: "23m", thumb: "", sprite: "https://todesvip.github.io/visor-manga/sprit/sprite2.vtt", spriteImg: "https://todesvip.github.io/visor-manga/sprit/sprite2.jpg", link: "https://ia801709.us.archive.org/29/items/seihou-shouka-saint-lime-1/Kaifuku%20Jutsushi%20no%20Yarinaoshi%2002.mkv", subtitulo: "https://todesvip.github.io/visor-manga/subtitles/Kaifuku Jutsushi no Yarinaoshi 02.spa.ass" },
            { num: 3, nombre: "Episodio 3", duracion: "24m", thumb: "", sprite: "https://todesvip.github.io/visor-manga/sprit/sprite3.vtt", spriteImg: "https://todesvip.github.io/visor-manga/sprit/sprite3.jpg", link: "https://ia801709.us.archive.org/29/items/seihou-shouka-saint-lime-1/Kaifuku%20Jutsushi%20no%20Yarinaoshi%2003.mkv", subtitulo: "https://todesvip.github.io/visor-manga/subtitles/Kaifuku Jutsushi no Yarinaoshi 03.spa.ass" },
            { num: 4, nombre: "Episodio 4", duracion: "24m", thumb: "", sprite: "https://todesvip.github.io/visor-manga/sprit/sprite4.vtt", spriteImg: "https://todesvip.github.io/visor-manga/sprit/sprite4.jpg", link: "https://ia801709.us.archive.org/29/items/seihou-shouka-saint-lime-1/Kaifuku%20Jutsushi%20no%20Yarinaoshi%2004.mkv", subtitulo: "https://todesvip.github.io/visor-manga/subtitles/Kaifuku Jutsushi no Yarinaoshi 04.spa.ass" },
            { num: 5, nombre: "Episodio 5", duracion: "24m", thumb: "", sprite: "https://todesvip.github.io/visor-manga/sprit/sprite5.vtt", spriteImg: "https://todesvip.github.io/visor-manga/sprit/sprite5.jpg", link: "https://ia601709.us.archive.org/29/items/seihou-shouka-saint-lime-1/Kaifuku%20Jutsushi%20no%20Yarinaoshi%2005.mkv", subtitulo: "https://todesvip.github.io/visor-manga/subtitles/Kaifuku Jutsushi no Yarinaoshi 05.spa.ass" },
            { num: 6, nombre: "Episodio 6", duracion: "24m", thumb: "", sprite: "https://todesvip.github.io/visor-manga/sprit/sprite6.vtt", spriteImg: "https://todesvip.github.io/visor-manga/sprit/sprite6.jpg", link: "https://ia801709.us.archive.org/29/items/seihou-shouka-saint-lime-1/Kaifuku%20Jutsushi%20no%20Yarinaoshi%2006.mkv", subtitulo: "https://todesvip.github.io/visor-manga/subtitles/Kaifuku Jutsushi no Yarinaoshi 06.spa.ass" },
            { num: 7, nombre: "Episodio 7", duracion: "24m", thumb: "", sprite: "https://todesvip.github.io/visor-manga/sprit/sprite7.vtt", spriteImg: "https://todesvip.github.io/visor-manga/sprit/sprite7.jpg", link: "https://ia801709.us.archive.org/29/items/seihou-shouka-saint-lime-1/Kaifuku%20Jutsushi%20no%20Yarinaoshi%2007.mkv", subtitulo: "https://todesvip.github.io/visor-manga/subtitles/Kaifuku Jutsushi no Yarinaoshi 07.spa.ass" },
            { num: 8, nombre: "Episodio 8", duracion: "24m", thumb: "", sprite: "https://todesvip.github.io/visor-manga/sprit/sprite8.vtt", spriteImg: "https://todesvip.github.io/visor-manga/sprit/sprite8.jpg", link: "https://ia801709.us.archive.org/29/items/seihou-shouka-saint-lime-1/Kaifuku%20Jutsushi%20no%20Yarinaoshi%2008.mkv", subtitulo: "https://todesvip.github.io/visor-manga/subtitles/Kaifuku Jutsushi no Yarinaoshi 08.spa.ass" },
            { num: 9, nombre: "Episodio 9", duracion: "24m", thumb: "", sprite: "https://todesvip.github.io/visor-manga/sprit/sprite9.vtt", spriteImg: "https://todesvip.github.io/visor-manga/sprit/sprite9.jpg", link: "https://ia801709.us.archive.org/29/items/seihou-shouka-saint-lime-1/Kaifuku%20Jutsushi%20no%20Yarinaoshi%2009.mkv", subtitulo: "https://todesvip.github.io/visor-manga/subtitles/Kaifuku Jutsushi no Yarinaoshi 09.spa.ass" },
            { num: 10, nombre: "Episodio 10", duracion: "24m", thumb: "", sprite: "https://todesvip.github.io/visor-manga/sprit/sprite10.vtt", spriteImg: "https://todesvip.github.io/visor-manga/sprit/sprite10.jpg", link: "https://ia801709.us.archive.org/29/items/seihou-shouka-saint-lime-1/Kaifuku%20Jutsushi%20no%20Yarinaoshi%2010.mkv", subtitulo: "https://todesvip.github.io/visor-manga/subtitles/Kaifuku Jutsushi no Yarinaoshi 10.spa.ass" },
            { num: 11, nombre: "Episodio 11", duracion: "24m", thumb: "", sprite: "https://todesvip.github.io/visor-manga/sprit/sprite11.vtt", spriteImg: "https://todesvip.github.io/visor-manga/sprit/sprite11.jpg", link: "https://ia801709.us.archive.org/29/items/seihou-shouka-saint-lime-1/Kaifuku%20Jutsushi%20no%20Yarinaoshi%2011.mkv", subtitulo: "https://todesvip.github.io/visor-manga/subtitles/Kaifuku Jutsushi no Yarinaoshi 11.spa.ass" },
            { num: 12, nombre: "Episodio 12", duracion: "24m", thumb: "", sprite: "https://todesvip.github.io/visor-manga/sprit/sprite12.vtt", spriteImg: "https://todesvip.github.io/visor-manga/sprit/sprite12.jpg", link: "https://ia801709.us.archive.org/29/items/seihou-shouka-saint-lime-1/Kaifuku%20Jutsushi%20no%20Yarinaoshi%2012.mkv", subtitulo: "https://todesvip.github.io/visor-manga/subtitles/Kaifuku Jutsushi no Yarinaoshi 12.spa.ass" }
        ]
    },
    {
        id: "Peter",
        titulo: "Peter Grill to Kenja no Jikan",
        titulo_jp: "ピーターグリルと賢者の時間",
        poster: "https://media.kitsu.app/anime/poster_images/42563/original.png",
        banner: "",
        rating: "18+",
        temporada: "Temporada 1",
        ano: "2020",
        calidad: "HD",
        sinopsis: "Peter Grill es el luchador más fuerte del mundo, pero su ascenso a la cima tuvo una consecuencia inesperada: ¡las mujeres de todo el mundo, tanto humanas como monstruos, quieren tener hijos genéticamente superiores! Dado que actualmente está comprometido con el amor de su vida, Peter no está muy interesado en su repentina popularidad, ¡y necesitará cada gramo de autocontrol para que Peter mantenga sus manos sobre sí mismo y su relación con su amante en una sola pieza!",
        episodios: [
            { num: 1, nombre: "Episodio 1", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20-%2001.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan - 01.es.ass" },
            { num: 2, nombre: "Episodio 2", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20-%2002.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan - 02.es.ass" },
            { num: 3, nombre: "Episodio 3", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20-%2003.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan - 03.es.ass" },
            { num: 4, nombre: "Episodio 4", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20-%2004.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan - 04.es.ass" },
            { num: 5, nombre: "Episodio 5", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20-%2005.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan - 05.es.ass" },
            { num: 6, nombre: "Episodio 6", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20-%2006.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan - 06.es.ass" },
            { num: 7, nombre: "Episodio 7", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20-%2007.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan - 07.es.ass" },
            { num: 8, nombre: "Episodio 8", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20-%2008.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan - 08.es.ass" },
            { num: 9, nombre: "Episodio 9", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20-%2009.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan - 09.es.ass" },
            { num: 10, nombre: "Episodio 10", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20-%2010.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan - 10.es.ass" },
            { num: 11, nombre: "Episodio 11", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20-%2011.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan - 11.es.ass" },
            { num: 12, nombre: "Episodio 12", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20-%2012.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan - 12.es.ass" }
        ]
    },
    {
        id: "Peter2",
        titulo: "Peter Grill to Kenja no Jikan Super Extra",
        titulo_jp: "ピーター・グリルと賢者の時間 Super Extra",
        poster: "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx141400-IHU8WRGMWrCh.jpg",
        banner: "",
        rating: "18+",
        temporada: "Temporada 1",
        ano: "2022",
        calidad: "HD",
        sinopsis: "La segunda temporada de Peter Grill para Kenja no Jikan. ¡Peter Grill está de regreso y listo para la acción! Entre sofocar una incursión de duendes, mejorar las negociaciones comerciales con los enanos y aplacar a una hermana vigilante que podría volverse loca para mantenerlo a raya, Peter tiene mucho trabajo por delante. Es el héroe más buscado del país... y eso sin contar la miríada de mujeres interesadas en sus \"otros\" talentos. Se necesitará hasta el último resto de la fuerza de voluntad de Peter para mantenerse concentrado en ser un héroe en otra atrevida temporada de Peter Grill and the Philosopher's Time - ¡Super Extra!",
        episodios: [
            { num: 1, nombre: "Episodio 1", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20S02E01.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan S02E01.es.ass" },
            { num: 2, nombre: "Episodio 2", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20S02E02.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan S02E02.es.ass" },
            { num: 3, nombre: "Episodio 3", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20S02E03.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan S02E03.es.ass" },
            { num: 4, nombre: "Episodio 4", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20S02E04.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan S02E04.es.ass" },
            { num: 5, nombre: "Episodio 5", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20S02E05.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan S02E05.es.ass" },
            { num: 6, nombre: "Episodio 6", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20S02E06.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan S02E06.es.ass" },
            { num: 7, nombre: "Episodio 7", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20S02E07.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan S02E07.es.ass" },
            { num: 8, nombre: "Episodio 8", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20S02E08.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan S02E08.es.ass" },
            { num: 9, nombre: "Episodio 9", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20S02E09.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan S02E09.es.ass" },
            { num: 10, nombre: "Episodio 10", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20S02E10.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan S02E10.es.ass" },
            { num: 11, nombre: "Episodio 11", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20S02E11.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan S02E11.es.ass" },
            { num: 12, nombre: "Episodio 12", duracion: "24m", thumb: "", sprite: "", spriteImg: "", link: "https://ia601802.us.archive.org/12/items/nazo-no-kanojo-x-01/Peter%20Grill%20to%20Kenja%20no%20Jikan%20S02E12.mkv", subtitulo: "https://Dimagemfondo.github.io/visor-imgen/src/Peter Grill to Kenja no Jikan S02E12.es.ass" }
        ]
    },
    {
        id: "Yuusha",
        titulo: "Yuusha Party ni Kawaii Ko ga Ita node, Kokuhaku shitemita",
        titulo_jp: "",
        poster: "https://raw.githubusercontent.com/Todesvip/visor-manga/main/cine/imagen/04.jpg",
        banner: "",
        rating: "16+",
        temporada: "1 Temporada",
        ano: "2026",
        calidad: "HD",
        sinopsis: "¡Youki murió en un accidente de tráfico y renació en un mundo fantástico! Sin embargo, en lugar de convertirse en el héroe de las leyendas, acabó reencarnándose en un demonio todopoderoso. Como no tenía ningún deseo de convertirse en el Señor de los Demonios, se quedó en el castillo del Señor de los Demonios como un guardián de bajo rango cualquiera. Un día, el grupo del héroe viene a atacar y, por capricho, él derrota a todo el grupo. Después de curar al grupo del héroe y prepararse para enviarlos de vuelta a la ciudad, se fija en la sacerdotisa y se enamora a primera vista.",
        episodios: [
            { num: 1, nombre: "Episodio 1", duracion: "24m", thumb: "", link: "" },
            { num: 2, nombre: "Episodio 2", duracion: "24m", thumb: "", link: "" }
        ]
    },
    {
        id: "Osananajimi",
        titulo: "Osananajimi to wa Love Comedy ni Naranai",
        titulo_jp: "幼馴染とはラブコメにならない",
        poster: "https://raw.githubusercontent.com/Todesvip/visor-manga/main/cine/imagen/06.jpg",
        banner: "",
        rating: "16+",
        temporada: "1 Temporada",
        ano: "2026",
        calidad: "HD",
        sinopsis: "El estudiante de secundaria Eiyuu tiene un dilema: ¡sus dos amigas de la infancia, Shio y Akari, se han convertido en dos chicas casi demasiado guapas! Aunque ellas no parecen darle mucha importancia, él no puede evitar verlas con otros ojos. Si alguna vez se dieran cuenta de cómo han cambiado sus sentimientos, ¡la vergüenza sería insoportable! Sin embargo, lo que Eiyuu no sabe es que Shio y Akari podrían sentir lo mismo por él. Un triángulo amoroso que se desarrolla lentamente, en el que todas las heroínas son amigas de la infancia, ¡tan frustrante como irresistible!",
        episodios: [
            { num: 1, nombre: "Episodio 1", duracion: "24m", thumb: "", link: "" },
            { num: 2, nombre: "Episodio 2", duracion: "24m", thumb: "", link: "" }
        ]
    }
];


