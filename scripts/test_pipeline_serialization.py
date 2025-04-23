import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    """
    Test that all pipeline configurations can be serialized without actually saving them.
    This is used to validate pipeline definitions in PRs.
    """
    # Import pipeline configurations
    from dc_custom_component.pipelines import dp_pipelines
    success = True

    # Test serialization for each pipeline configuration
    for pipeline_config in dp_pipelines:
        workspace = pipeline_config.get("workspace", "unknown")
        name = pipeline_config.get("name", "unknown")
        
        # Test query pipeline serialization
        query_pipeline = pipeline_config["query"]
        if query_pipeline:
            try:
                logger.info(f"Testing serialization of {workspace}/{name} query pipeline")
                query_pipeline.dumps()  # Just test if it works, don't need the result
                logger.info(f"Successfully serialized {workspace}/{name} query pipeline")
            except Exception as e:
                logger.error(f"Error serializing {workspace}/{name} query pipeline: {str(e)}")
                success = False
        
        # Test indexing pipeline serialization if it exists
        indexing_pipeline = pipeline_config.get("indexing")
        if indexing_pipeline:
            try:
                logger.info(f"Testing serialization of {workspace}/{name} indexing pipeline")
                yaml_str = indexing_pipeline.dumps()
                logger.info(f"Successfully serialized {workspace}/{name} indexing pipeline")
            except Exception as e:
                logger.error(f"Error serializing {workspace}/{name} indexing pipeline: {str(e)}")
                success = False
    
    if success:
        logger.info("All pipelines serialized successfully!")
        return 0
    else:
        logger.error("Some pipelines failed to serialize. Check the logs above for details.")
        return 1


if __name__ == "__main__":
    exit(main())
