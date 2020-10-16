TARGET?=main
BIBER=$(shell biber -v 2>/dev/null)
XELATEX=$(shell xelatex -v 2>/dev/null)
ifneq ($(XELATEX),)
	COMPILER=xelatex
else
	COMPILER=pdflatex
endif

PDFTEXOPTS = -halt-on-error

ifneq ($(BIBER),)
	TARGET_CMD="\def\usebusybiber{1} \input{$(TARGET).tex}"
	BIBER_CMD=biber
	BIBER_OPT=$(TARGET)
else
	TARGET_CMD="$(TARGET).tex"
	BIBER_CMD=bibtex
	BIBER_OPT=$(TARGET).aux
endif
default: build



clean:
	rm -f *.acn *.acr *.alg *.aux *.bbl *.blg *.dvi *.glg *.glo *.gls *.ist *.lof *.log *.lol *.lot *.out *.pdf *.toc *.pdfsync *.gz *.tdo *.xml *.gz *.bcf *.nav *.snm


once:
	$(COMPILER) $(PDFTEXOPTS) $(TARGET_CMD)


build:	
	$(COMPILER) $(PDFTEXOPTS) $(TARGET_CMD)
	$(BIBER_CMD) $(BIBER_OPT)
	makeindex -s $(TARGET).ist -t $(TARGET).glg -o $(TARGET).gls $(TARGET).glo
	makeindex -s $(TARGET).ist -t $(TARGET).alg -o $(TARGET).acr $(TARGET).acn
	$(COMPILER) $(PDFTEXOPTS) $(TARGET_CMD)
	$(COMPILER) $(PDFTEXOPTS) $(TARGET_CMD)

