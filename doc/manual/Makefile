xsltproc = xsltproc --nonet \
 --param section.autolabel 1 \
 --param section.label.includes.component.label 1 \
 --param html.stylesheet \'style.css\' \
 --param xref.with.number.and.title 1 \
 --param toc.section.depth 3 \
 --param admon.style \'\' \
 --param callout.graphics.extension \'.gif\' \
 --param contrib.inline.enabled 0

docbookxsl = $(HOME)/.nix-profile/xml/xsl/docbook

all: manual.html man

manual.html: *.xml
	$(xsltproc) --xinclude --stringparam profile.condition manual \
	  $(docbookxsl)/profiling/profile.xsl manual.xml | \
	  $(xsltproc) --output manual.html $(docbookxsl)/html/docbook.xsl -

man: *.xml
	$(xsltproc) --xinclude --stringparam profile.condition manpage \
	  $(docbookxsl)/profiling/profile.xsl manual.xml | \
	  $(xsltproc) $(docbookxsl)/manpages/docbook.xsl -

install: all
	mkdir -p $(mandir)/man1
	cp charon.1 $(mandir)/man1
	mkdir -p $(docdir)
	cp manual.html style.css $(docdir)
