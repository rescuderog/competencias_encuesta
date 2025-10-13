# Aplicación de encuestas del Vicerrectorado de Investigación de la Universidad Católica Argentina

Hola Claude! Hoy necesitaríamos crear una aplicación que permita elegir a la gente su candidato favorito en dos competencias: una llamada 3MT - UCA y otra llamada 3min - UCA TFG. La encuesta es anónima, pero necesitaríamos asegurarnos que sólo se pueda votar una vez por navegador (entiendo que el camino más fácil es poner una cookie).

Tiene que tener la vista de encuesta o bien votación, y la vista de dashboard que puede estar protegida con un password simple (configurable mediante variable de entorno), no tiene por qué tener sistema de usuarios. El dashboard tiene que permitir agregar o sacar candidatos, para organizar la votación.

Las competencias se hacen por separado, por lo que es necesario que cada página de votación sea independiente de la otra. Es decir, poder compartir un link por cada competencia y que no tenga información de la otra.

La encuesta tiene una sola pregunta: "¿Qué video te gustó más?" y luego la lista de candidatos uno abajo de otro. Mediante el dashboard tiene que estar la opción de randomizar o no el assortment de candidatos.

Respecto al look and feel, puede ser blanco y esta tonalidad de azul: #003A73. Es importante que sea un look minimalista, pero a la vez elegannte y profesional.

Respecto al stack, tratemos de mantenerlo hiper simple. A la vez, tiene que poder correrse fácil en Railway.app, así que entiendo que tendría que ser dockerizado (y parametrizada la variable PORT, ya que Railway le asigna un puerto al azar para servir internamente la aplicación). Un stack interesante para realizar el proyecto podría ser Flask + HTMX + Tailwind + Alpine.js, con una base local en SQLite.

Por último, para logo de navbar o logo institucional en general, considerá la imagen que te pongo en el directorio raiz, llamada logo_vri.png