# ex10dead-book-bibliography

A bibliography is a list of bibliography entries. A bibliography file is a text file that lists your sources, a file where you can write detailed and nested bibliography entries as plain text. For example: each entry can hold more than one web address.
The format that makes it possible is the [sourcetree datafile format](https://github.com/freywald/sourcetree-datafile-format).

*ex10dead-book-bibliography* is part of the larger *ex10dead-book* library. It gives you three things you can use together: a converter for PDF and HTML, an offline archiver, and a web server.

## The PDF and HTML converters

The converters take your bibliography text file and turn it into a beautiful HTML page or a beautiful PDF document. You get a document you can read, print, or share.

## The offline archiver
The archiver reads the bibliography and saves a local offline copy of each web address. You can use one method, or several, for the same address.

- **gallery-dl** downloads a twitter/x.com tweet as JSON together with its images and videos.
- **json-to-html** rebuilds a twitter/x.com tweet and its replies from the downloaded JSON into one static HTML page.


- **screenshot** saves a master high-resolution picture of the page. For x.com it includes a short thread of replies on X.
- **singlefile** saves the page as one self-contained HTML file.


- **wget** downloads the page and the files it needs, and stores them in a zip.
- **wget-text** downloads the page as HTML with most media left out.

## The internal web server

The web server lets you open and browse the whole archive from the bibliography. You can look through the saved pages, pictures, and files in one place.

