PLUGIN_DIR := calibre_plugin
ZIP := opds_client.zip

.PHONY: build clean

build:
	cd $(PLUGIN_DIR) && zip -r ../$(ZIP) . \
		-x "__pycache__/*" "*.pyc" ".DS_Store" "*/.DS_Store"
	zip $(ZIP) README.md
	@echo "Built $(ZIP)"

clean:
	rm -f $(ZIP)
